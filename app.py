from fastapi import FastAPI
import chromadb
import ollama

app = FastAPI()
chroma = chromadb.PersistentClient(path="./db")
ollama_client = ollama.Client(host="http://host.docker.internal:11434")

# List of all dataset collections
datasets = ["SCC", "FCA", "FC", "TCC", "CMAC", "CHRT", "SST", "RPD", "RAD", "RLLR", "ONCA"]

@app.post("/query")
def query(q: str, collection_name: str = None):
    """
    Query across all collections or a specific collection.
    If collection_name is provided, query only that collection.
    Otherwise, query all collections and return the best match.
    """
    if collection_name:
        # Query specific collection
        collection = chroma.get_collection(f"{collection_name}_docs")
        results = collection.query(query_texts=[q], n_results=1)
        context = results["documents"][0][0] if results["documents"] else ""
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
            except Exception as e:
                # Collection might not exist yet, skip it
                continue
        
        context = best_context

    answer = ollama_client.generate(
        model="tinyllama",
        prompt=f"Context:\n{context}\n\nQuestion: {q}\n\nAnswer clearly and concisely:"
    )

    return {"answer": answer["response"]}
