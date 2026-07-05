"""Cleans up raw LLM completions before they're returned to the client."""
import re
from typing import Sequence

# Different models restate the question differently before answering: some
# echo it verbatim, some rephrase it as their own question, some wrap it in a
# label ("Question:", "You asked:"), and some prefix the actual answer with a
# label of its own ("Answer:"). All of these are stripped so the API only
# ever returns the answer text (the caller appends "urls" separately).
_QUESTION_LABELS = (
    "question:", "q:", "you asked:", "your question:",
    "you're asking", "you are asking", "you want to know",
    "to answer your question,",
)
_ANSWER_LABELS = ("response:", "answer:", "a:")

# Filler some models open with, independent of the question itself.
_PREAMBLE_PATTERNS = (
    re.compile(r"^(sure|okay|ok|certainly|of course)[!,.]?\s*", re.IGNORECASE),
    re.compile(r"^(based on|according to)\b[^.\n]*?,\s*", re.IGNORECASE),
    re.compile(r"^here('s| is)[^.\n]*?[:.]\s*", re.IGNORECASE),
)

# Isolates a response's first sentence so it can be checked in isolation - a
# leading sentence phrased as a question is almost always the model
# restating/rephrasing the user's question rather than answering it (the
# prompts in prompts.py explicitly tell every role not to do this).
_SENTENCE_END = re.compile(r"[.?!\n]")

# Punctuation/label remnants left right after an echoed question is cut out,
# e.g. the "?" or ":" that used to separate it from the real answer.
_LEADING_JUNK = " \n\"'?.!:,"


def clean_response(response_text: str, query: str) -> str:
    text = response_text.strip()
    query = query.strip()

    # Models sometimes stack several of the above in one response (e.g. a
    # rephrased question in a "Question:" label, followed by an "Answer:"
    # label with a filler preamble) so strip in rounds until stable.
    for _ in range(4):
        before = text
        text = _strip_label(text, _QUESTION_LABELS)
        text = _strip_echoed_question(text, query)
        text = _strip_label(text, _ANSWER_LABELS)
        text = _strip_preamble(text)
        if text == before:
            break

    return text.strip(" \n\"'")


def _strip_echoed_question(text: str, query: str) -> str:
    candidate = text.lstrip(" \n\"'")
    if query and candidate.lower().startswith(query.lower()):
        return candidate[len(query):].lstrip(_LEADING_JUNK)

    match = _SENTENCE_END.search(text)
    if match and text[match.start()] == "?":
        return text[match.end():].lstrip(_LEADING_JUNK)
    return text


def _strip_preamble(text: str) -> str:
    for pattern in _PREAMBLE_PATTERNS:
        stripped = pattern.sub("", text, count=1)
        if stripped != text:
            return stripped.strip()
    return text


def _strip_label(text: str, labels: Sequence[str]) -> str:
    stripped = text.lstrip()
    lower = stripped.lower()
    for label in labels:
        if lower.startswith(label):
            return stripped[len(label):].strip()
    return text
