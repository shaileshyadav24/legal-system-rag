"""Turns recent chat messages (from services/chat_service.py) into the history block injected into prompts."""
from typing import Any, Dict, List


def build_history_context(messages: List[Dict[str, Any]]) -> str:
    if not messages:
        return ""
    lines = "\n".join(f"Q: {message['query']}\nA: {message['answer']}" for message in messages)
    return f"\nPrevious conversation:\n{lines}\n"
