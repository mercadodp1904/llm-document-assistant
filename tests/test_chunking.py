import pytest

from chunking import split_text


def test_split_text_creates_overlapping_chunks() -> None:
    chunks = split_text("abcdefghij", chunk_size=6, overlap=2)

    assert chunks == ["abcdef", "efghij", "ij"]


def test_split_text_rejects_invalid_overlap() -> None:
    with pytest.raises(ValueError):
        split_text("text", chunk_size=4, overlap=4)