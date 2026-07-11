"""CRUD for chat sessions/messages backing server-side chat history."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from libs.shared.db import chat_messages_collection, chat_sessions_collection

# tinyllama has a small context window - without a cap, the prompt (and
# generation latency) would grow every turn for a long-running session.
MAX_HISTORY_TURNS = 5


def _object_id(value: str, detail: str) -> ObjectId:
    try:
        return ObjectId(value)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail) from exc


def _get_owned_session(user_id: ObjectId, session_id: str) -> Dict[str, Any]:
    session = chat_sessions_collection.find_one({
        "_id": _object_id(session_id, "Session not found"),
        "user_id": user_id,
    })
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


def get_or_create_session(user_id: ObjectId, session_id: Optional[str], role: str, query: str) -> Dict[str, Any]:
    if session_id:
        return _get_owned_session(user_id, session_id)

    now = datetime.now(timezone.utc)
    session = {
        "user_id": user_id,
        "role": role,
        "title": query[:60],
        "created_at": now,
        "updated_at": now,
    }
    result = chat_sessions_collection.insert_one(session)
    session["_id"] = result.inserted_id
    return session


def load_recent_messages(session_id: ObjectId, limit: int = MAX_HISTORY_TURNS) -> List[Dict[str, Any]]:
    messages = list(
        chat_messages_collection.find({"session_id": session_id})
        .sort("created_at", -1)
        .limit(limit)
    )
    return list(reversed(messages))


def load_history_for_session(user_id: ObjectId, session_id: Optional[str]) -> List[Dict[str, Any]]:
    """
    Recent turns for `session_id`, or [] for a brand-new conversation (no
    session_id yet - there's nothing to load). Deliberately doesn't create a
    new session as a side effect, so a query that ends up finding no context
    doesn't leave behind an empty orphan session.
    """
    if not session_id:
        return []
    session = _get_owned_session(user_id, session_id)
    return load_recent_messages(session["_id"])


def save_message(session_id: ObjectId, user_id: ObjectId, query: str, answer: str, urls: List[str]) -> None:
    now = datetime.now(timezone.utc)
    chat_messages_collection.insert_one({
        "session_id": session_id,
        "user_id": user_id,
        "query": query,
        "answer": answer,
        "urls": urls,
        "created_at": now,
    })
    chat_sessions_collection.update_one({"_id": session_id}, {"$set": {"updated_at": now}})


def list_sessions(user_id: ObjectId) -> List[Dict[str, Any]]:
    return list(chat_sessions_collection.find({"user_id": user_id}).sort("updated_at", -1))


def get_session_messages(user_id: ObjectId, session_id: str) -> List[Dict[str, Any]]:
    session = _get_owned_session(user_id, session_id)
    return list(chat_messages_collection.find({"session_id": session["_id"]}).sort("created_at", 1))


def delete_session(user_id: ObjectId, session_id: str) -> None:
    session = _get_owned_session(user_id, session_id)
    chat_messages_collection.delete_many({"session_id": session["_id"]})
    chat_sessions_collection.delete_one({"_id": session["_id"]})
