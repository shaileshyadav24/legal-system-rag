"""Retrieves the most relevant chunk of context for a query from ChromaDB."""
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

chroma = chromadb.PersistentClient(path="./db")
# Same default embedding function collections were created with in dataset/dataset.py.
# Kept as one instance and reused so a query is only embedded once, not once per dataset.
default_ef = DefaultEmbeddingFunction()

_URL_PATTERN = re.compile(r"https?://[^\s]+")


def _query_one(dataset: str, query_embedding: List[float]) -> Optional[Dict[str, Any]]:
    """Query a single "<dataset>_docs" collection. Returns None if it doesn't exist or has no match."""
    try:
        collection = chroma.get_collection(f"{dataset}_docs")
        results = collection.query(query_embeddings=[query_embedding], n_results=1)
    except Exception:
        return None
    if not results["documents"] or not results["documents"][0]:
        return None
    return {
        "distance": results["distances"][0][0],
        "context": results["documents"][0][0],
        "metadata": results["metadatas"][0][0] if results.get("metadatas") and results["metadatas"][0] else None,
    }


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
    Find the best-matching context for `q`: either in one named collection, or
    across all `datasets` queried in parallel, keeping the closest match.
    """
    # Embed once and reuse across every collection lookup instead of
    # re-embedding the same query text once per dataset.
    query_embedding = default_ef([q])[0]

    if collection_name:
        match = _query_one(collection_name, query_embedding)
        if match is None:
            return {"error": f"Collection {collection_name}_docs not found"}
        context = match["context"]
        best_metadata = match["metadata"]
        pdf_links = _extract_pdf_links(best_metadata)
    else:
        context = ""
        best_metadata = None
        pdf_links = []
        best_distance = float("inf")
        with ThreadPoolExecutor(max_workers=len(datasets)) as executor:
            futures = [executor.submit(_query_one, dataset, query_embedding) for dataset in datasets]
            for future in as_completed(futures):
                match = future.result()
                if match is not None and match["distance"] < best_distance:
                    best_distance = match["distance"]
                    context = match["context"]
                    best_metadata = match["metadata"]

    return {
        "context": context,
        "urls": _extract_urls(context) if context else [],
        "metadata": best_metadata,
        "pdf_links": pdf_links,
    }
