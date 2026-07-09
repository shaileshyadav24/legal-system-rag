import concurrent.futures
import sys
import time
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from pymongo.errors import BulkWriteError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Allow `python dataset/dataset.py` to import the `services` package regardless
# of the invoking working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.db import documents_collection, ensure_connection, ensure_vector_search_index  # noqa: E402

DATASETS = ["SCC", "FCA", "FC", "TCC", "CMAC", "CHRT", "SST", "RPD", "RAD", "RLLR", "ONCA"]

URL_PREFIX = "https://huggingface.co/datasets/a2aj/canadian-case-law/resolve/main/"
MAX_WORKERS = 6
BATCH_SIZE = 1000

# Same embedding model retrieval (services/retrieval.py) queries with - must match
# so ingested vectors and query vectors live in the same embedding space.
default_ef = DefaultEmbeddingFunction()


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504))
    # Reuse TCP/TLS connections across the worker threads instead of
    # re-handshaking on every request.
    adapter = HTTPAdapter(max_retries=retry, pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def download_dataset(session: requests.Session, dataset: str) -> tuple[str, pd.DataFrame | None]:
    url = f"{URL_PREFIX}{dataset}/train.parquet"
    start = time.perf_counter()
    try:
        response = session.get(url, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Error downloading {dataset}: {exc}")
        return dataset, None

    df = pd.read_parquet(BytesIO(response.content))
    elapsed = time.perf_counter() - start
    size_mb = len(response.content) / 1e6
    print(f"Downloaded {dataset} ({size_mb:.1f} MB) in {elapsed:.1f}s")
    return dataset, df


def ingest_dataset(dataset: str, df: pd.DataFrame) -> None:
    # Only reached once this dataset's fetch has already succeeded (see
    # main()) - safe to replace its existing documents wholesale so stale/
    # removed records don't linger alongside the freshly fetched ones.
    deleted = documents_collection.delete_many({"dataset": dataset}).deleted_count
    print(f"  Cleared {deleted} existing docs for {dataset}")

    records = df.to_dict(orient="records")
    documents = []
    ids = []
    for i, record in enumerate(records):
        doc = record.get("text") or record.get("content") or record.get("body") or str(record)
        documents.append(doc)
        ids.append(str(record.get("id", f"{dataset}_doc_{i}")))

    total = len(documents)
    for start in range(0, total, BATCH_SIZE):
        end = min(start + BATCH_SIZE, total)
        batch_ids = ids[start:end]
        batch_texts = documents[start:end]
        embeddings = default_ef(batch_texts)

        docs = [
            {
                "_id": f"{dataset}_{doc_id}",
                "dataset": dataset,
                "text": text,
                # Cast from numpy.float32 (what DefaultEmbeddingFunction returns) to
                # native floats - BSON can't encode numpy scalar types.
                "embedding": [float(x) for x in embedding],
            }
            for doc_id, text, embedding in zip(batch_ids, batch_texts, embeddings)
        ]
        try:
            documents_collection.insert_many(docs, ordered=False)
        except BulkWriteError as exc:
            # Existing docs for this dataset were already cleared above, so a
            # duplicate _id here means the source data itself repeats an id -
            # safe to ignore; anything else re-raises.
            if any(error["code"] != 11000 for error in exc.details.get("writeErrors", [])):
                raise
        print(f"  Ingested {end}/{total} docs for {dataset}")
    print(f"Ingested {dataset} into case_law_documents")


def main() -> None:
    # Fail fast if MongoDB isn't reachable, before spending time downloading
    # multi-GB datasets that would just fail to store anyway.
    ensure_connection()

    session = _build_session()
    overall_start = time.perf_counter()

    # Downloads are network-bound, so fetch every dataset concurrently instead
    # of one HTTP round trip at a time. Ingestion (embedding + Mongo writes)
    # stays on the main thread and overlaps with in-flight downloads.
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(download_dataset, session, dataset): dataset for dataset in DATASETS}
        for future in concurrent.futures.as_completed(futures):
            dataset, df = future.result()
            if df is None:
                print(f"Error: {dataset} data is None")
                continue
            ingest_dataset(dataset, df)

    ensure_vector_search_index()
    print(f"Done in {time.perf_counter() - overall_start:.1f}s")


if __name__ == "__main__":
    main()
