import pytest

from retriever import InMemoryRetriever


def test_search_returns_chunks_by_cosine_similarity() -> None:
    embed_query = lambda _: [[1.0, 0.0]]
    retriever = InMemoryRetriever(
        ["close", "far"],
        [[1.0, 0.0], [0.0, 1.0]],
        embed_query,
    )

    assert retriever.search("question", top_k=1) == ["close"]


def test_retriever_rejects_mismatched_data() -> None:
    with pytest.raises(ValueError):
        InMemoryRetriever(["one"], [], lambda _: [[1.0]])