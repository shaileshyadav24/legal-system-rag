from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from service import query_collections
import ollama

ollama_client = ollama.Client()

datasets = ["SCC", "FCA", "FC", "TCC", "CMAC", "CHRT", "SST", "RPD", "RAD", "RLLR", "ONCA"]

class QueryRequest(BaseModel):
    query: str
    collection_name: Optional[str] = None

router = APIRouter()

@router.post("/query/user")
def query(request: QueryRequest):
    query = request.query
    collection_name = request.collection_name
    result = query_collections(query, collection_name, datasets)
    # Handle error from service
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])

    context = result.get("context", "")
    url_links = result.get("urls", [])
    conversation_history = request.dict().get("history", [])

    history_context = ""
    if conversation_history:
        history_context = "\n".join([f"Q: {msg['q']}\nA: {msg['answer']}" for msg in conversation_history])
        history_context = f"\nPrevious conversation:\n{history_context}\n"

    if not context:
        raise HTTPException(status_code=status.HTTP_204_NO_CONTENT, detail="No relevant context found for the query.")

    prompt = f"""You are a friendly and patient legal assistant helping someone who has no legal background or training. Your goal is to make legal information accessible and understandable to everyday people.

When answering questions:
1. Use plain, everyday language instead of legal jargon. If you must use legal terms, explain them in simple words.
2. Break down complex concepts into easy-to-understand steps or explanations.
3. Be clear and direct - provide practical guidance that helps the person understand what they need to know.
4. If the context mentions specific procedures, deadlines, or requirements, explain them in simple terms with examples when helpful.
5. Be empathetic and reassuring - legal matters can be confusing and stressful for non-lawyers.
6. Focus on what the person needs to know to take action or make informed decisions.

Do NOT repeat or restate the question. Start your response immediately with a clear, helpful answer.

{history_context}
Context from legal documents:
{context}

Question: {query}

Provide a helpful answer in plain language:"""
    try:
        answer = ollama_client.generate(
            model="tinyllama",
            prompt=prompt
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Model generation failed: {str(e)}")

    response_text = answer["response"]
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
    return {
        "answer": response_text,
        "urls": url_links if url_links else []
    }


@router.post("/query/lawyer")
def queryLawyer(request: QueryRequest):
    query = request.query
    collection_name = request.collection_name
    result = query_collections(query, collection_name, datasets)
    # Handle error from service
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])

    context = result.get("context", "")
    url_links = result.get("urls", [])
    conversation_history = request.dict().get("history", [])

    history_context = ""
    if conversation_history:
        history_context = "\n".join([f"Q: {msg['q']}\nA: {msg['answer']}" for msg in conversation_history])
        history_context = f"\nPrevious conversation:\n{history_context}\n"

    if not context:
        raise HTTPException(status_code=status.HTTP_204_NO_CONTENT, detail="No relevant context found for the query.")

    prompt = f"""You are a legal assistant helping a lawyer or judge. Your goal is to provide clear, concise, and accurate legal information, using appropriate legal terminology and referencing relevant legal principles or precedents when necessary.

When answering questions:
1. Use precise legal language and terminology, but ensure clarity and avoid unnecessary complexity.
2. Reference relevant statutes, case law, or legal doctrines where applicable.
3. Provide structured, logically organized responses that facilitate legal analysis or decision-making.
4. If the context mentions specific procedures, deadlines, or requirements, explain them with reference to legal standards or rules.
5. Focus on the legal reasoning and implications, supporting your answer with citations or examples when helpful.
6. Assume the reader has a legal background and is seeking information to inform legal arguments or judicial decisions.

Do NOT repeat or restate the question. Start your response immediately with a clear, substantive answer.

{history_context}
Context from legal documents:
{context}

Question: {query}

Provide a legally sound and well-reasoned answer:"""

    try:
        answer = ollama_client.generate(
            model="tinyllama",
            prompt=prompt
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Model generation failed: {str(e)}")

    response_text = answer["response"]
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
    return {
        "answer": response_text,
        "urls": url_links if url_links else []
    }
