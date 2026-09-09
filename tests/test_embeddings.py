from unittest.mock import patch

from embeddings import generate_embeddings


def test_generate_embeddings_uses_configured_model() -> None:
    with patch("sentence_transformers.SentenceTransformer") as model_class:
        model_class.return_value.encode.return_value.tolist.return_value = [[0.1, 0.2]]

        result = generate_embeddings(["hello"], model_name="test-model")

    model_class.assert_called_once_with("test-model")
    assert result == [[0.1, 0.2]]


def test_generate_embeddings_returns_empty_for_no_texts() -> None:
    assert generate_embeddings([]) == []