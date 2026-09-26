import pytest

from chunking import split_text


def test_split_text_overlaps_whole_atomic_units() -> None:
    chunks = split_text("First sentence. Second sentence. Third sentence.", chunk_size=35, overlap=10)

    assert chunks == [
        "First sentence. Second sentence.",
        "Second sentence. Third sentence.",
    ]


def test_resume_heading_stays_with_first_bullet() -> None:
    text = "PROJECTS\n• NaviCav navigation app\n• Built with Python\nEDUCATION\n• BS Computer Science"

    chunks = split_text(text, chunk_size=45, overlap=5)

    assert any(
        "PROJECTS" in chunk and "• NaviCav navigation app" in chunk
        for chunk in chunks
    )


def test_thesis_headings_start_new_chunks() -> None:
    text = (
        "I. INTRODUCTION\nThis paper studies transport networks.\n"
        "II. RELATED WORK\nPrior work examines routing.\n"
        "A. Some Subsection\nThe subsection presents a model."
    )

    chunks = split_text(text, chunk_size=80, overlap=10)

    assert chunks[0].startswith("I. INTRODUCTION")
    assert chunks[1].startswith("II. RELATED WORK")
    assert chunks[2].startswith("A. Some Subsection")


def test_et_al_does_not_end_a_sentence() -> None:
    chunks = split_text(
        "Smith et al. proposed a method. It works well.",
        chunk_size=100,
        overlap=10,
    )

    assert chunks == ["Smith et al. proposed a method. It works well."]


def test_reference_entries_are_not_split() -> None:
    text = "[1] Philippine Statistics Authority. Annual report.\n[2] Census results."

    chunks = split_text(text, chunk_size=60, overlap=5)

    assert all("[1]" in chunk and "Annual report." in chunk for chunk in chunks if "[1]" in chunk)
    assert all("[2]" in chunk and "Census results." in chunk for chunk in chunks if "[2]" in chunk)


def test_oversized_atomic_unit_is_safely_sliced() -> None:
    chunks = split_text("A" * 2_000, chunk_size=500, overlap=50)

    assert chunks
    assert all(len(chunk) <= 500 for chunk in chunks)


def test_split_text_rejects_invalid_overlap() -> None:
    with pytest.raises(ValueError):
        split_text("text", chunk_size=4, overlap=4)


def test_split_text_rejects_invalid_chunk_size() -> None:
    with pytest.raises(ValueError):
        split_text("text", chunk_size=0)


def test_split_text_returns_empty_for_empty_input() -> None:
    assert split_text("  \n\t") == []