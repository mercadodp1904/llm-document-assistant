"""Utilities for splitting document text into structure-aware chunks."""

import re


_ABBREVIATIONS = (
    "et al.",
    "vol.",
    "no.",
    "fig.",
    "eq.",
    "jan.",
    "feb.",
    "mar.",
    "apr.",
    "jun.",
    "jul.",
    "aug.",
    "sep.",
    "oct.",
    "nov.",
    "dec.",
)

_SENTENCE_BOUNDARY = re.compile(r"[.!?](?=\s+[A-Z])")
_REFERENCE = re.compile(r"^\s*\[\d+\]")


def _is_heading(line: str) -> bool:
    """Return whether a line matches one of the supported heading forms."""
    stripped_line = line.strip()
    letters = re.findall(r"[A-Z]", stripped_line)
    all_caps = bool(re.fullmatch(r"[A-Z][A-Z\s&'()/,\-]*", stripped_line))
    roman_heading = bool(re.match(r"^[IVXLCDM]+\.\s+[A-Z]", stripped_line))
    letter_heading = bool(
        re.fullmatch(r"[A-Z]\.\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*", stripped_line)
    )
    return (all_caps and len(letters) >= 8) or roman_heading or letter_heading


def _split_sentences(text: str) -> list[str]:
    """Split prose at sentence boundaries while preserving abbreviations."""
    sentences: list[str] = []
    start = 0
    for match in _SENTENCE_BOUNDARY.finditer(text):
        prefix = text[start : match.end()].rstrip().lower()
        if any(prefix.endswith(abbreviation) for abbreviation in _ABBREVIATIONS):
            continue
        sentence = text[start : match.end()].strip()
        if sentence:
            sentences.append(sentence)
            start = match.end()

    remainder = text[start:].strip()
    if remainder:
        sentences.append(remainder)
    return sentences


def _atomic_units(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Detect atomic units and slice only units that exceed the size limit."""
    units: list[str] = []
    for line in text.splitlines():
        stripped_line = line.strip()
        if not stripped_line:
            continue
        if _is_heading(stripped_line) or stripped_line.startswith("•") or _REFERENCE.match(
            stripped_line
        ):
            units.append(stripped_line)
        else:
            units.extend(_split_sentences(stripped_line))

    expanded_units: list[str] = []
    step = chunk_size - overlap
    for unit in units:
        if len(unit) <= chunk_size:
            expanded_units.append(unit)
            continue
        expanded_units.extend(
            unit[start : start + chunk_size]
            for start in range(0, len(unit), step)
        )
    return expanded_units


def split_text(
    text: str,
    chunk_size: int = 1_000,
    overlap: int = 200,
) -> list[str]:
    """Split text into greedily packed chunks of structure-aware units."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be between zero and chunk_size - 1")

    cleaned_text = text.strip()
    if not cleaned_text:
        return []

    units = _atomic_units(cleaned_text, chunk_size, overlap)
    chunks: list[str] = []
    current_units: list[str] = []

    for unit in units:
        is_heading = _is_heading(unit)
        if is_heading and current_units:
            chunks.append(" ".join(current_units))
            current_units = [unit]
            continue

        candidate = " ".join((*current_units, unit))
        if current_units and len(candidate) > chunk_size:
            chunks.append(" ".join(current_units))
            last_unit = current_units[-1]
            current_units = [last_unit]
            candidate = " ".join((*current_units, unit))
            if len(candidate) > chunk_size:
                chunks.append(last_unit)
                current_units = [unit]
            else:
                current_units.append(unit)
        else:
            current_units.append(unit)

    if current_units:
        chunks.append(" ".join(current_units))
    return chunks