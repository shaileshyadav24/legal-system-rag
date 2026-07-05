"""FastAPI routes for the RAG query endpoints."""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from services.auth import get_current_user
from services.chat_service import get_or_create_session, load_recent_messages, save_message
from services.constants import DATASETS
from services.history import build_history_context
from services.llm import generate_answer
from services.models import QueryRequest
from services.response_utils import clean_response
from services.retrieval import query_collections

router = APIRouter()


def _handle_query(role: str, request: QueryRequest, user: Dict[str, Any]) -> dict:
    result = query_collections(request.query, request.collection_name, DATASETS)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])

    context = result.get("context", "")
    if not context:
        raise HTTPException(
            status_code=status.HTTP_204_NO_CONTENT,
            detail="No relevant context found for the query.",
        )

    session = get_or_create_session(user["_id"], request.session_id, role, request.query)
    history_context = build_history_context(load_recent_messages(session["_id"]))
    raw_answer = generate_answer(role, history_context, context, request.query)
    answer = clean_response(raw_answer, request.query)
    urls = result.get("urls") or []

    save_message(session["_id"], user["_id"], request.query, answer, urls)

    return {
        "answer": answer,
        "urls": urls,
        "session_id": str(session["_id"]),
    }


@router.post("/query/user")
def query_user(request: QueryRequest, user: Dict[str, Any] = Depends(get_current_user)) -> dict:
    return _handle_query("user", request, user)


@router.post("/query/lawyer")
def query_lawyer(request: QueryRequest, user: Dict[str, Any] = Depends(get_current_user)) -> dict:
    return _handle_query("lawyer", request, user)
