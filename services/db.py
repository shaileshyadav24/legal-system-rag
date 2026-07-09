"""Owns the single MongoDB client and collection handles, plus index setup."""
from pymongo import ASCENDING, MongoClient
from pymongo.errors import OperationFailure, PyMongoError
from pymongo.operations import SearchIndexModel

from services.config import MONGODB_DB_NAME, MONGODB_URI

client = MongoClient(MONGODB_URI)
db = client[MONGODB_DB_NAME]


def ensure_connection() -> None:
    """
    Fail fast with a clear error if MongoDB isn't reachable, instead of
    letting the first real write fail deep inside some other call path (e.g.
    after downloading a multi-GB dataset in dataset/dataset.py).
    """
    try:
        client.admin.command("ping")
    except PyMongoError as exc:
        raise RuntimeError(
            f"Could not connect to MongoDB at {MONGODB_URI!r} (db={MONGODB_DB_NAME!r}). "
            "Check that MongoDB is running/reachable and MONGODB_URI/MONGODB_DB_NAME are correct."
        ) from exc

users_collection = db["users"]
chat_sessions_collection = db["chat_sessions"]
chat_messages_collection = db["chat_messages"]
documents_collection = db["case_law_documents"]
revoked_tokens_collection = db["revoked_tokens"]
password_reset_tokens_collection = db["password_reset_tokens"]
rate_limit_attempts_collection = db["rate_limit_attempts"]

# Name of the Atlas Search vector index on documents_collection.embedding.
# Must match the index used in services/retrieval.py's $vectorSearch stage.
VECTOR_INDEX_NAME = "case_law_vector_index"

# Dimensionality of chromadb.utils.embedding_functions.DefaultEmbeddingFunction
# (all-MiniLM-L6-v2), reused here so ingestion and retrieval stay in sync.
EMBEDDING_DIMENSIONS = 384


def ensure_indexes() -> None:
    """Create the regular (non-vector) indexes needed by the app. Idempotent."""
    users_collection.create_index("email", unique=True)
    chat_sessions_collection.create_index([("user_id", ASCENDING)])
    chat_messages_collection.create_index([("session_id", ASCENDING), ("created_at", ASCENDING)])
    documents_collection.create_index("dataset")
    revoked_tokens_collection.create_index("jti", unique=True)
    # TTL indexes: MongoDB auto-deletes the doc once the stored `expires_at`
    # is in the past, so revoked/reset entries clean themselves up.
    revoked_tokens_collection.create_index("expires_at", expireAfterSeconds=0)
    password_reset_tokens_collection.create_index("token_hash", unique=True)
    password_reset_tokens_collection.create_index("expires_at", expireAfterSeconds=0)
    rate_limit_attempts_collection.create_index([("identifier", ASCENDING), ("endpoint", ASCENDING)])
    # TTL: each attempt record expires on its own after the rate-limit window,
    # so the window "resets" naturally without any separate cleanup logic.
    rate_limit_attempts_collection.create_index("expires_at", expireAfterSeconds=0)


def ensure_vector_search_index() -> None:
    """
    Create the Atlas Search vector index on documents_collection, if it
    doesn't already exist. Only works against a MongoDB Atlas cluster - Atlas
    Search is not available on a plain self-hosted mongod.
    """
    definition = {
        "fields": [
            {
                "type": "vector",
                "path": "embedding",
                "numDimensions": EMBEDDING_DIMENSIONS,
                "similarity": "cosine",
            },
            {"type": "filter", "path": "dataset"},
        ]
    }
    model = SearchIndexModel(definition=definition, name=VECTOR_INDEX_NAME, type="vectorSearch")
    try:
        documents_collection.create_search_index(model)
    except OperationFailure as exc:
        # Index already exists - safe to ignore so this can be called on every startup/ingest run.
        if "already exists" not in str(exc).lower():
            raise
