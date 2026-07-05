"""Turns prior chat turns into the history block injected into prompts."""
from typing import List, Optional

from services.models import HistoryTurn

# tinyllama has a small context window - without a cap, the prompt (and
# generation latency) would grow every turn for a long-running session.
MAX_HISTORY_TURNS = 5


def build_history_context(history: Optional[List[HistoryTurn]]) -> str:
    if not history:
        return ""
    recent_turns = history[-MAX_HISTORY_TURNS:]
    lines = "\n".join(f"Q: {turn.q}\nA: {turn.answer}" for turn in recent_turns)
    return f"\nPrevious conversation:\n{lines}\n"
