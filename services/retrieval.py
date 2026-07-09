"""Retrieves the most relevant chunk of context for a query via MongoDB Atlas Vector Search."""
import re
from typing import Any, Dict, List, Optional

from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from services.db import VECTOR_INDEX_NAME, documents_collection

# Same default embedding function documents were ingested with in dataset/dataset.py.
# Kept as one instance and reused so a query is only embedded once.
default_ef = DefaultEmbeddingFunction()

_URL_PATTERN = re.compile(r"https?://[^\s]+")

# Candidates Atlas scans before ranking. Wider than what the old per-dataset
# fan-out needed, since one query now has to find the global best match
# across every dataset in a single pass instead of comparing 11 top-1s.
_NUM_CANDIDATES = 200


def _extract_pdf_links(metadata: Optional[Dict[str, Any]]) -> List[str]:
    if not metadata:
        return []
    return [
        value for key, value in metadata.items()
        if isinstance(value, str) and (value.endswith(".pdf") or "pdf" in key.lower() or "link" in key.lower())
    ]


def _extract_urls(text: str) -> List[str]:
    return [url.rstrip(".,;:'\"") for url in _URL_PATTERN.findall(text)]


def query_collections(q: str, collection_name: Optional[str], datasets: List[str]) -> Dict[str, Any]:
    """
    Find the best-matching case-law chunk for `q` via a single $vectorSearch
    aggregation against the consolidated case_law_documents collection,
    optionally filtered to one dataset.
    """
    if collection_name and collection_name not in datasets:
        return {"error": f"Collection {collection_name} not found"}

    query_embedding = default_ef([q])[0]

    vector_search_stage: Dict[str, Any] = {
        "index": VECTOR_INDEX_NAME,
        "path": "embedding",
        # Cast from numpy.float32 (what DefaultEmbeddingFunction returns) to
        # native floats - BSON can't encode numpy scalar types.
        "queryVector": [float(x) for x in query_embedding],
        "numCandidates": _NUM_CANDIDATES,
        "limit": 1,
    }
    if collection_name:
        vector_search_stage["filter"] = {"dataset": collection_name}

    pipeline = [
        {"$vectorSearch": vector_search_stage},
        {"$project": {"text": 1, "metadata": 1, "_id": 0}},
    ]
    results = list(documents_collection.aggregate(pipeline))

    if not results:
        return {"context": "", "urls": [], "metadata": None, "pdf_links": []}

    best = results[0]
    context = best["text"]
    metadata = best.get("metadata")

    return {
        "context": context,
        "urls": _extract_urls(context),
        "metadata": metadata,
        "pdf_links": _extract_pdf_links(metadata),
    }
