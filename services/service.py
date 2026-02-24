import re
from typing import Optional, List, Dict, Any
import chromadb

chroma = chromadb.PersistentClient(path="./db")

def query_collections(q: str, collection_name: Optional[str], datasets: List[str]) -> Dict[str, Any]:
    pdf_links = []
    context = ""
    best_metadata = None

    if collection_name:
        # Query specific collection
        try:
            collection = chroma.get_collection(f"{collection_name}_docs")
            results = collection.query(query_texts=[q], n_results=1)
            context = results["documents"][0][0] if results["documents"] else ""
            # Extract metadata if available
            if results.get("metadatas") and results["metadatas"][0]:
                metadata = results["metadatas"][0][0]
                # Check for PDF link in metadata
                for key, value in metadata.items():
                    if isinstance(value, str) and (value.endswith('.pdf') or 'pdf' in key.lower() or 'link' in key.lower()):
                        pdf_links.append(value)
        except Exception as e:
            return {"error": f"Collection {collection_name}_docs not found"}
    else:
        # Query all collections and get the best match
        best_context = ""
        best_distance = float('inf')
        for dataset in datasets:
            try:
                collection = chroma.get_collection(f"{dataset}_docs")
                results = collection.query(query_texts=[q], n_results=1)
                if results["documents"] and results["distances"]:
                    distance = results["distances"][0][0]
                    if distance < best_distance:
                        best_distance = distance
                        best_context = results["documents"][0][0]
                        # Store metadata from best match
                        if results.get("metadatas") and results["metadatas"][0]:
                            best_metadata = results["metadatas"][0][0]
            except Exception:
                continue
        context = best_context

    # Extract and clean URLs from context
    url_links = []
    if context:
        pdf_pattern = r'https?://[^\s]+'
        url_links = re.findall(pdf_pattern, context)
        url_links = [url.rstrip('.,;:\'"') for url in url_links]

    return {
        "context": context,
        "urls": url_links,
        "metadata": best_metadata,
        "pdf_links": pdf_links
    }
