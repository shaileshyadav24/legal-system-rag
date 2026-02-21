import chromadb
import pandas as pd
import requests
from io import BytesIO

client = chromadb.PersistentClient(path="./db")

datasets = ["SCC",
            "FCA",
            "FC",
            "TCC",
            "CMAC",
            "CHRT",
            "SST",
            "RPD",
            "RAD",
            "RLLR",
            "ONCA"
]

url_prefix = "https://huggingface.co/datasets/a2aj/canadian-case-law/resolve/main/"

# # load data
# results = requests.get(url)

# download the parquet files into a pandas df
for dataset in datasets:
    df_temp = None
    url = f"{url_prefix}{dataset}/train.parquet"
    print(f"Downloading {dataset} data from {url}")
    results = requests.get(url)
    df_temp = pd.read_parquet(BytesIO(results.content))
    
    if df_temp is None:
        print(f"Error: {dataset} data is None")
    else:
        # Create a separate collection for each dataset
        collection = client.get_or_create_collection(f"{dataset}_docs")
        
        # Extract text from records (ChromaDB expects list of strings)
        records = df_temp.to_dict(orient="records")
        documents = []
        ids = []
        for i, record in enumerate(records):
            # Try to find text field, otherwise stringify the record
            doc = record.get("text") or record.get("content") or record.get("body") or str(record)
            documents.append(doc)
            ids.append(str(record.get("id", f"{dataset}_doc_{i}")) if isinstance(record, dict) else f"{dataset}_doc_{i}")
        
        # Add in batches for better performance
        BATCH_SIZE = 1000
        total = len(documents)
        for start in range(0, total, BATCH_SIZE):
            end = min(start + BATCH_SIZE, total)
            batch_docs = documents[start:end]
            batch_ids = ids[start:end]
            collection.add(documents=batch_docs, ids=batch_ids)
            print(f"  Added {end}/{total} to {dataset}_docs collection")
        print(f"Exported {dataset} to {dataset}_docs collection")
