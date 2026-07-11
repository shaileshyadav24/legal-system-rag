"""FastAPI routes for browsing and managing a user's chat sessions."""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, status

from apps.chat.chat_service import delete_session, get_session_messages, list_sessions
from libs.shared.jwt_auth import get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])


def _serialize_session(session: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(session["_id"]),
        "role": session["role"],
        "title": session["title"],
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
    }


def _serialize_message(message: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "query": message["query"],
        "answer": message["answer"],
        "urls": message.get("urls") or [],
        "created_at": message["created_at"],
    }


@router.get("/sessions")
def get_sessions(user: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    return [_serialize_session(session) for session in list_sessions(user["_id"])]


@router.get("/sessions/{session_id}/messages")
def get_messages(session_id: str, user: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    return [_serialize_message(message) for message in get_session_messages(user["_id"], session_id)]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_session(session_id: str, user: Dict[str, Any] = Depends(get_current_user)) -> None:
    delete_session(user["_id"], session_id)
