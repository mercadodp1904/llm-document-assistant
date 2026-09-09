"""Simple in-memory cosine-similarity retrieval."""

from collections.abc import Callable, Sequence
import math


EmbeddingFunction = Callable[[Sequence[str]], list[list[float]]]


class InMemoryRetriever:
    """Store chunk vectors in memory and retrieve the most similar chunks."""

    def __init__(
        self,
        chunks: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        embed_query: EmbeddingFunction,
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        self.chunks = list(chunks)
        self.embeddings = [list(vector) for vector in embeddings]
        self.embed_query = embed_query

    def search(self, query: str, top_k: int = 3) -> list[str]:
        """Return up to ``top_k`` chunks ordered by cosine similarity."""
        if top_k <= 0 or not self.chunks:
            return []

        query_vectors = self.embed_query([query])
        if not query_vectors:
            return []
        return [
            chunk
            for _, chunk in self.search_with_embedding(query_vectors[0], top_k)
        ]

    def search_with_embedding(
        self,
        query_vector: Sequence[float],
        top_k: int = 3,
    ) -> list[tuple[float, str]]:
        """Return scored chunks for an already-generated query embedding."""
        if top_k <= 0 or not self.chunks:
            return []

        scored_chunks = [
            (self._cosine_similarity(query_vector, vector), chunk)
            for chunk, vector in zip(self.chunks, self.embeddings)
        ]
        scored_chunks.sort(key=lambda item: item[0], reverse=True)
        return scored_chunks[:top_k]

    @staticmethod
    def _cosine_similarity(
        first: Sequence[float],
        second: Sequence[float],
    ) -> float:
        if len(first) != len(second):
            raise ValueError("embedding vectors must have the same dimensions")
        first_norm = math.sqrt(sum(value * value for value in first))
        second_norm = math.sqrt(sum(value * value for value in second))
        if first_norm == 0 or second_norm == 0:
            return 0.0
        dot_product = sum(left * right for left, right in zip(first, second))
        return dot_product / (first_norm * second_norm)