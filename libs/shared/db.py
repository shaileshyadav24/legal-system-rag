"""Owns the single MongoDB client and collection handles, plus index setup."""
from pymongo import ASCENDING, MongoClient
from pymongo.errors import OperationFailure, PyMongoError
from pymongo.operations import SearchIndexModel

from libs.shared.config import MONGODB_DB_NAME, MONGODB_URI

# Explicit timeouts so a network partition to Atlas hangs a request for at
# most ~10s instead of indefinitely (pymongo's own default has no
# socketTimeoutMS at all - a socket that goes dead after connecting would
# otherwise block forever).
client = MongoClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=10000,
)
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
password_reset_tokens_collection = db["password_reset_tokens"]

# Name of the Atlas Search vector index on documents_collection.embedding.
# Must match the index used in apps/chat/retrieval.py's $vectorSearch stage.
VECTOR_INDEX_NAME = "case_law_vector_index"

# Dimensionality of chromadb.utils.embedding_functions.DefaultEmbeddingFunction
# (all-MiniLM-L6-v2), reused here so ingestion and retrieval stay in sync.
EMBEDDING_DIMENSIONS = 384


def ensure_auth_indexes() -> None:
    """Indexes for collections the auth service owns. Idempotent."""
    users_collection.create_index("email", unique=True)
    # TTL index: MongoDB auto-deletes the doc once the stored `expires_at` is
    # in the past, so reset entries clean themselves up. (Revoked tokens and
    # rate-limit attempts live in Redis instead - see libs/shared/redis_client.py.)
    password_reset_tokens_collection.create_index("token_hash", unique=True)
    password_reset_tokens_collection.create_index("expires_at", expireAfterSeconds=0)


def ensure_chat_indexes() -> None:
    """Indexes for collections the chat/query service owns. Idempotent."""
    chat_sessions_collection.create_index([("user_id", ASCENDING)])
    chat_messages_collection.create_index([("session_id", ASCENDING), ("created_at", ASCENDING)])
    documents_collection.create_index("dataset")


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
