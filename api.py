from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from service import query_collections
from prompts import get_user_prompt, get_lawyer_prompt
import ollama

router = APIRouter()

ollama_client = ollama.Client()

datasets = ["SCC", "FCA", "FC", "TCC", "CMAC", "CHRT", "SST", "RPD", "RAD", "RLLR", "ONCA"]

class QueryRequest(BaseModel):
    query: str
    collection_name: Optional[str] = None
    history: Optional[list] = None

def build_history_context(conversation_history):
    if conversation_history:
        history_context = "\n".join([f"Q: {msg['q']}\nA: {msg['answer']}" for msg in conversation_history])
        return f"\nPrevious conversation:\n{history_context}\n"
    return ""

def clean_response(response_text, query):
    q_lower = query.lower().strip()
    response_lower = response_text.lower().strip()
    if response_lower.startswith(q_lower):
        response_text = response_text[len(query):].strip()
        for prefix in ["Question:", "Q:", "question:", "q:"]:
            if response_text.lower().startswith(prefix.lower()):
                response_text = response_text[len(prefix):].strip()
    response_text = response_text.strip()
    for prefix in ["Response:", "response:", "Answer:", "answer:"]:
        if response_text.lower().startswith(prefix.lower()):
            response_text = response_text[len(prefix):].strip()
            break
    return response_text

def build_prompt(role, history_context, context, query):
    if role == "user":
        return get_user_prompt(history_context, context, query)
    elif role == "lawyer":
        return get_lawyer_prompt(history_context, context, query)
    else:
        return ""

@router.post("/query/user")
def query(request: QueryRequest):
    query = request.query
    collection_name = request.collection_name
    result = query_collections(query, collection_name, datasets)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    context = result.get("context", "")
    url_links = result.get("urls", [])
    conversation_history = request.dict().get("history", [])
    history_context = build_history_context(conversation_history)
    if not context:
        raise HTTPException(status_code=status.HTTP_204_NO_CONTENT, detail="No relevant context found for the query.")
    prompt = build_prompt("user", history_context, context, query)
    try:
        answer = ollama_client.generate(
            model="tinyllama",
            prompt=prompt
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Model generation failed: {str(e)}")
    response_text = clean_response(answer["response"], query)
    return {
        "answer": response_text,
        "urls": url_links if url_links else []
    }


@router.post("/query/lawyer")
def queryLawyer(request: QueryRequest):
    query = request.query
    collection_name = request.collection_name
    result = query_collections(query, collection_name, datasets)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    context = result.get("context", "")
    url_links = result.get("urls", [])
    conversation_history = request.dict().get("history", [])
    history_context = build_history_context(conversation_history)
    if not context:
        raise HTTPException(status_code=status.HTTP_204_NO_CONTENT, detail="No relevant context found for the query.")
    prompt = build_prompt("lawyer", history_context, context, query)
    try:
        answer = ollama_client.generate(
            model="tinyllama",
            prompt=prompt
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Model generation failed: {str(e)}")
    response_text = clean_response(answer["response"], query)
    return {
        "answer": response_text,
        "urls": url_links if url_links else []
    }
