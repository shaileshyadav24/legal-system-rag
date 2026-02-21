from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import chromadb
import ollama

app = FastAPI()
chroma = chromadb.PersistentClient(path="./db")
ollama_client = ollama.Client()

# List of all dataset collections
datasets = ["SCC", "FCA", "FC", "TCC", "CMAC", "CHRT", "SST", "RPD", "RAD", "RLLR", "ONCA"]

class QueryRequest(BaseModel):
    q: str
    collection_name: Optional[str] = None

@app.post("/query")
def query(request: QueryRequest):
    """
    Query across all collections or a specific collection.
    If collection_name is provided, query only that collection.
    Otherwise, query all collections and return the best match.
    """
    q = request.q
    collection_name = request.collection_name
    
    if collection_name:
        # Query specific collection
        try:
            collection = chroma.get_collection(f"{collection_name}_docs")
            results = collection.query(query_texts=[q], n_results=1)
            context = results["documents"][0][0] if results["documents"] else ""
        except Exception as e:
            return {"error": f"Collection {collection_name}_docs not found"}
    else:
        # Query all collections and get the best match
        best_context = ""
        best_distance = float('inf')
        
        for dataset in datasets:
            print(f"Querying {dataset} collection")
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
    
    print(f"Context: {context}")
    
    prompt = f"""You are a legal assistant helping a customer with no legal background.

Context from legal documents:
{context}

Question: {q}

Instructions:
- Answer clearly and concisely in plain language
- Include the case name and section number if mentioned in the context
- If a PDF link is available in the context, include it
- Do not include any information not found in the context
- Keep your response brief and easy to understand

Answer:"""
    
    answer = ollama_client.generate(
        model="tinyllama",
        prompt=prompt
    )

    return {"answer": answer["response"]}
