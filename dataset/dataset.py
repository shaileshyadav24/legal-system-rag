import concurrent.futures
import time
from io import BytesIO

import chromadb
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

client = chromadb.PersistentClient(path="./db")

DATASETS = ["SCC", "FCA", "FC", "TCC", "CMAC", "CHRT", "SST", "RPD", "RAD", "RLLR", "ONCA"]

URL_PREFIX = "https://huggingface.co/datasets/a2aj/canadian-case-law/resolve/main/"
MAX_WORKERS = 6
BATCH_SIZE = 1000


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
    collection = client.get_or_create_collection(f"{dataset}_docs")

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
        collection.add(documents=documents[start:end], ids=ids[start:end])
        print(f"  Added {end}/{total} to {dataset}_docs collection")
    print(f"Exported {dataset} to {dataset}_docs collection")


def main() -> None:
    session = _build_session()
    overall_start = time.perf_counter()

    # Downloads are network-bound, so fetch every dataset concurrently instead
    # of one HTTP round trip at a time. Ingestion (embedding + chroma writes)
    # stays on the main thread and overlaps with in-flight downloads.
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(download_dataset, session, dataset): dataset for dataset in DATASETS}
        for future in concurrent.futures.as_completed(futures):
            dataset, df = future.result()
            if df is None:
                print(f"Error: {dataset} data is None")
                continue
            ingest_dataset(dataset, df)

    print(f"Done in {time.perf_counter() - overall_start:.1f}s")


if __name__ == "__main__":
    main()
