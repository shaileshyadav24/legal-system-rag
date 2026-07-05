"""FastAPI routes for the RAG query endpoints."""
from fastapi import APIRouter, HTTPException, status

from services.constants import DATASETS
from services.history import build_history_context
from services.llm import generate_answer
from services.models import QueryRequest
from services.response_utils import clean_response
from services.retrieval import query_collections

router = APIRouter()


def _handle_query(role: str, request: QueryRequest) -> dict:
    result = query_collections(request.query, request.collection_name, DATASETS)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])

    context = result.get("context", "")
    if not context:
        raise HTTPException(
            status_code=status.HTTP_204_NO_CONTENT,
            detail="No relevant context found for the query.",
        )

    history_context = build_history_context(request.history)
    raw_answer = generate_answer(role, history_context, context, request.query)

    return {
        "answer": clean_response(raw_answer, request.query),
        "urls": result.get("urls") or [],
    }


@router.post("/query/user")
def query_user(request: QueryRequest) -> dict:
    return _handle_query("user", request)


@router.post("/query/lawyer")
def query_lawyer(request: QueryRequest) -> dict:
    return _handle_query("lawyer", request)
