"""Utilities for splitting document text into overlapping chunks."""


def split_text(
    text: str,
    chunk_size: int = 1_000,
    overlap: int = 200,
) -> list[str]:
    """Split text into character-based chunks with a fixed overlap."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be between zero and chunk_size - 1")

    cleaned_text = text.strip()
    if not cleaned_text:
        return []

    step = chunk_size - overlap
    return [
        cleaned_text[start : start + chunk_size]
        for start in range(0, len(cleaned_text), step)
    ]