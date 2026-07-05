"""Cleans up raw LLM completions before they're returned to the client."""
from typing import Sequence

# tinyllama tends to echo the question back and/or prefix its answer with a
# label; both are stripped so the API returns just the answer text.
_QUESTION_PREFIXES = ("Question:", "Q:")
_ANSWER_PREFIXES = ("Response:", "Answer:")


def clean_response(response_text: str, query: str) -> str:
    response_text = response_text.strip()
    query = query.strip()

    if response_text.lower().startswith(query.lower()):
        response_text = response_text[len(query):].strip()
        response_text = _strip_leading_prefix(response_text, _QUESTION_PREFIXES)

    return _strip_leading_prefix(response_text, _ANSWER_PREFIXES)


def _strip_leading_prefix(text: str, prefixes: Sequence[str]) -> str:
    lower = text.lower()
    for prefix in prefixes:
        if lower.startswith(prefix.lower()):
            return text[len(prefix):].strip()
    return text
