"""Wraps the Ollama client: builds the role-specific prompt and generates an answer."""
from fastapi import HTTPException, status

import ollama
from prompts.prompts import get_lawyer_prompt, get_user_prompt

_MODEL = "tinyllama"
_PROMPT_BUILDERS = {
    "user": get_user_prompt,
    "lawyer": get_lawyer_prompt,
}

client = ollama.Client()


def generate_answer(role: str, history_context: str, context: str, query: str) -> str:
    build_prompt = _PROMPT_BUILDERS.get(role)
    if build_prompt is None:
        raise ValueError(f"Unknown role: {role!r}")

    prompt = build_prompt(history_context, context, query)
    try:
        result = client.generate(model=_MODEL, prompt=prompt)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model generation failed: {e}",
        ) from e
    return result["response"]
