"""FastAPI routes for the RAG query endpoints."""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from apps.chat.chat_service import get_or_create_session, load_history_for_session, save_message
from apps.chat.constants import DATASETS
from apps.chat.history import build_history_context, build_search_query
from apps.chat.llm import generate_answer
from apps.chat.models import QueryRequest
from apps.chat.response_utils import clean_response
from apps.chat.retrieval import query_collections
from libs.shared.jwt_auth import get_current_user

router = APIRouter()


def _handle_query(role: str, request: QueryRequest, user: Dict[str, Any]) -> dict:
    # Loaded before retrieval (not just before generation) so a follow-up
    # question can be embedded together with recent turns - see
    # build_search_query for why a bare follow-up retrieves badly on its own.
    history_messages = load_history_for_session(user["_id"], request.session_id)
    history_context = build_history_context(history_messages)
    search_query = build_search_query(history_messages, request.query)

    result = query_collections(search_query, request.collection_name, DATASETS)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])

    context = result.get("context", "")
    if not context:
        raise HTTPException(
            status_code=status.HTTP_204_NO_CONTENT,
            detail="No relevant context found for the query.",
        )

    raw_answer = generate_answer(role, history_context, context, request.query)
    answer = clean_response(raw_answer, request.query)
    urls = result.get("urls") or []

    session = get_or_create_session(user["_id"], request.session_id, role, request.query)
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
