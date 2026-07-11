"""Wraps the Ollama client: builds the role-specific prompt and generates an answer."""
import logging

from fastapi import HTTPException, status

import ollama
from apps.chat.prompts import get_lawyer_prompt, get_user_prompt
from libs.shared.config import OLLAMA_HOST, OLLAMA_MODEL

logger = logging.getLogger(__name__)

_PROMPT_BUILDERS = {
    "user": get_user_prompt,
    "lawyer": get_lawyer_prompt,
}

client = ollama.Client(host=OLLAMA_HOST)


def generate_answer(role: str, history_context: str, context: str, query: str) -> str:
    build_prompt = _PROMPT_BUILDERS.get(role)
    if build_prompt is None:
        raise ValueError(f"Unknown role: {role!r}")

    prompt = build_prompt(history_context, context, query)
    try:
        result = client.generate(model=OLLAMA_MODEL, prompt=prompt)
    except Exception as e:
        # Logged server-side (with the real cause) rather than put in the
        # response - the raw exception string can carry internal details
        # (e.g. the Ollama host) that shouldn't reach the client.
        logger.exception("Ollama generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Model generation failed",
        ) from e
    return result["response"]
