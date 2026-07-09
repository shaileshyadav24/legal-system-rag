"""Turns recent chat messages (from services/chat_service.py) into the history block injected into prompts, and into the text retrieval embeds."""
from typing import Any, Dict, List


def build_history_context(messages: List[Dict[str, Any]]) -> str:
    if not messages:
        return ""
    lines = "\n".join(f"Q: {message['query']}\nA: {message['answer']}" for message in messages)
    return f"\nPrevious conversation:\n{lines}\n"


def build_search_query(messages: List[Dict[str, Any]], query: str) -> str:
    """
    Combines the current query with recent conversation turns for retrieval,
    not just generation. A bare follow-up like "what about that specifically?"
    shares almost no keywords with the actual topic, so embedding it alone
    tends to retrieve an unrelated document chunk - which is what makes a
    multi-turn chat look like it "lost context" even though the history text
    is still present in the generation prompt.

    `query` is kept first since DefaultEmbeddingFunction truncates long input
    from the end, and the current question must never be the part dropped.
    """
    if not messages:
        return query
    recent = " ".join(f"{message['query']} {message['answer']}" for message in messages)
    return f"{query} {recent}"
