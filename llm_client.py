"""Thin wrapper around the Google Gemini API."""

import os

try:
    from google import genai
except ImportError:  # pragma: no cover - exercised when dependencies are absent
    genai = None


DEFAULT_MODEL = "gemini-3.6-flash"


def answer_question(
    question: str,
    context: list[str],
    model: str = DEFAULT_MODEL,
    history: list[dict] | None = None,
) -> str:
    """Ask the configured model to answer using only retrieved context."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not configured")
    if genai is None:
        raise RuntimeError("google-genai is not installed")

    context_text = "\n\n".join(context)
    history_text = "\n\n".join(
        f"User: {turn['question']}\nAssistant: {turn['answer']}"
        for turn in history or []
    )
    history_section = (
        f"Previous conversation:\n{history_text}\n\n"
        "Use the previous conversation only to resolve references such as "
        '"it" or "that"; do not use it as a source of facts.\n\n'
        if history_text
        else ""
    )
    prompt = (
        "Answer the question using only the context below. "
        "If the answer is not in the context, say you do not know.\n\n"
        f"{history_section}"
        f"Context:\n{context_text}\n\n"
        f"Question: {question}"
    )
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text