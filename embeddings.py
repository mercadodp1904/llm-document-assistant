"""Embedding generation backed by sentence-transformers."""

from collections.abc import Sequence


DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def generate_embeddings(
    texts: Sequence[str],
    model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> list[list[float]]:
    """Generate one embedding vector for each text.

    The model is loaded lazily so importing the application does not trigger a
    model download. Callers can pass a model name for local experimentation.
    """
    if not texts:
        return []

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    vectors = model.encode(list(texts), convert_to_numpy=True)
    return vectors.tolist()