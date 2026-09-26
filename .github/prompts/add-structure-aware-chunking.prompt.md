---
mode: agent
---

# Replace fixed-size chunking with structure-aware chunking

## Context

`chunking.py` currently splits document text purely by character count:

```python
def split_text(text: str, chunk_size: int = 1_000, overlap: int = 200) -> list[str]:
    ...
    step = chunk_size - overlap
    return [cleaned_text[start : start + chunk_size] for start in range(0, len(cleaned_text), step)]
```

This has no awareness of document structure. Verified against two real uploaded documents
(`pypdf`-extracted text from a resume PDF and an IEEE-format thesis paper PDF), this causes:

- Mid-sentence and mid-word cuts (e.g. `"...version control"` / `"(Git), manual software testing..."`
  split across two chunks)
- A section heading landing in a different chunk from its own content (e.g. `PROJECTS` heading
  separated from the `NaviCav` project title/bullets that follow it)
- Two unrelated sections glued into a single chunk with no boundary (e.g. the tail of the
  `NaviCav` bullets and the entire `Quantibids` title+bullets ending up in one chunk), which
  dilutes the embedding for both and hurts retrieval precision
- Bracket-numbered references (`[1] Philippine Statistics Authority...`) getting arbitrarily
  split mid-citation

Retriever/consumer contract that MUST NOT change:
- `split_text(text, chunk_size, overlap) -> list[str]` — same signature, same return type
- `retriever.py`'s `InMemoryRetriever` only requires `len(chunks) == len(embeddings)`, index-aligned,
  and does not care about chunk structure — so this is a drop-in replacement inside `chunking.py` only
- `api/routes.py` calls `split_text(text)` with defaults and passes the result straight to
  `generate_embeddings(chunks)` and `save_session_document(...)` — no other file should need changes

## Requirements for the new `chunking.py`

Implement chunking as a two-phase process: **split into atomic units** that must never be broken
across a chunk boundary, then **greedily pack** those units into chunks up to `chunk_size`.

### Phase 1 — atomic unit detection (in priority order)

1. **Headings** — a line matching any of:
   - An ALL-CAPS run of ≥8 letters total (e.g. `TECHNICAL SKILLS`, `EXPERIENCE`) — excludes short
     acronyms like `SDLC`, `OOP`, `MERN`, `QA` from false-triggering
   - Roman numeral + period + caps, e.g. `I. INTRODUCTION`, `II. RELATED WORK`
   - Single capital letter + period + Title Case, e.g. `A. Transportation Network Modeling`
2. **Bracket-numbered reference entries** — a line/segment starting with `[n]` (e.g.
   `[1] Philippine Statistics Authority...`) — treat like a bullet, never split mid-citation
3. **Bullets** — any `•`-marked line is its own atomic unit
4. **Sentences** — remaining prose is split on sentence boundaries (`.`/`!`/`?` followed by
   whitespace + a capital letter), BUT must not false-trigger on common abbreviations. Guard
   against at least: `et al.`, `vol.`, `no.`, `Fig.`, `Eq.`, `Jan.`, `Feb.`, `Mar.`, `Apr.`,
   `Jun.`, `Jul.`, `Aug.`, `Sep.`, `Oct.`, `Nov.`, `Dec.`
5. **Character fallback** — if any single atomic unit from steps 1-4 is still longer than
   `chunk_size` on its own (e.g. one huge unbroken paragraph with no sentence breaks), fall back
   to the old fixed-size character slicing *for that one oversized unit only*. This guarantees the
   function can never infinite-loop or return an unbounded chunk.

### Phase 2 — greedy packing

Walk the atomic units in original document order. Append each unit to the current chunk's buffer
as long as adding it would not exceed `chunk_size`; when it would, close the current chunk and
start a new one with that unit. This guarantees a heading always lands in the same chunk as at
least its first following unit (bullet/sentence), instead of the current bug where a heading can
be stranded with the previous section's tail.

### Overlap

Carry forward the **last atomic unit** (not a raw character tail) from the end of the previous
chunk into the start of the next chunk, so overlap is always a whole bullet/sentence/reference
rather than a mid-sentence character fragment.

### Function signature (unchanged)

```python
def split_text(text: str, chunk_size: int = 1_000, overlap: int = 200) -> list[str]:
```

Keep the existing validation (`chunk_size > 0`, `0 <= overlap < chunk_size`) and the existing
`cleaned_text = text.strip()` / empty-text-returns-`[]` behavior.

## Tests to add (pytest)

Add these to the existing chunking test file (or create one if none exists), following the
project's existing regression-test style (see `test_auth.py` for conventions):

1. A resume-style fixture (heading + prose + bullets, no blank lines between sections — mirrors
   the real messy `pypdf` extraction) asserting that a section heading and its first bullet always
   land in the same chunk
2. A thesis-style fixture with `I. INTRODUCTION`, `II. RELATED WORK`, `A. Some Subsection` headings
   on their own lines, asserting each heading starts a new chunk rather than being buried mid-chunk
3. A sentence-splitting regression test containing `"et al."` mid-sentence, asserting it is NOT
   treated as a sentence boundary
4. A bracket-numbered references fixture (`[1] ...`, `[2] ...`) asserting no chunk boundary falls
   inside a single `[n]` entry
5. A safety-net test: one atomic unit deliberately longer than `chunk_size` (e.g. a 2000-character
   unbroken sentence with `chunk_size=500`), asserting the function still returns chunks no larger
   than `chunk_size` and does not raise or hang
6. Keep/adapt any existing tests asserting `split_text` returns `[]` for empty input and raises
   `ValueError` on invalid `chunk_size`/`overlap`

## Implementation notes

- Keep the module interview-explainable: prefer straightforward regex + a simple state machine
  over a parsing library, consistent with the rest of the project's "no hidden magic" philosophy
- Do not change `retriever.py`, `api/routes.py`, or any embedding/storage code — this should be a
  self-contained change to `chunking.py` (and its test file) only
- After implementing, run `.\venv\Scripts\python.exe -m pytest` (not bare `pytest`) and confirm all
  existing tests plus the new ones pass
- Do not proceed to further roadmap items (e.g. the "stuff-if-small" hybrid retrieval idea) — this
  prompt is scoped to chunking only
