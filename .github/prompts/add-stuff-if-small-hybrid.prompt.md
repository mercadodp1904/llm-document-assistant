---
mode: agent
---

# Add "stuff-if-small, retrieve-if-large" hybrid to /ask

## Context

`gemini-3.6-flash` has a ~1M token context window. For small document sets, running the full
embed → cosine-similarity-search → top-k pipeline is unnecessary overhead — the full text can be
passed directly to the model. Retrieval should only kick in once total content exceeds a token
threshold.

This branches ON TOP OF the existing structure-aware chunking work (already merged) — the
"large document" fallback path IS the current chunked-retrieval pipeline, unchanged.

## 1. Schema change: store raw document text (`api/auth.py`)

`session_documents` currently stores only post-chunking `chunks` and `vectors` — the original
extracted text is discarded in `/upload` after `split_text()` runs. To decide stuff-vs-retrieve
and to build full-text context, the raw pre-chunking text must be persisted.

- Add a `raw_text TEXT NOT NULL` column to `session_documents`
- **IMPORTANT**: `init_session_documents_table` uses `CREATE TABLE IF NOT EXISTS`, which will NOT
  add this column to any existing local `users.db` created before this change. Add an explicit
  migration step in `init_session_documents_table` (or a new `_migrate_session_documents_table`
  called from `init_db`) that checks `PRAGMA table_info(session_documents)` for `raw_text` and
  runs `ALTER TABLE session_documents ADD COLUMN raw_text TEXT NOT NULL DEFAULT ''` if it's
  missing, so existing local databases don't break on the next run
- Update `save_session_document(session_id, filename, chunks, vectors, raw_text)` — new
  `raw_text: str` parameter, included in the `INSERT`
- Update `get_session_documents` — `SELECT` must include `raw_text` so callers in `routes.py` can
  read it back

## 2. `llm_client.py` additions

Refactor the duplicated client-setup logic (API key check, `genai is None` check) out of
`answer_question` into a shared helper, then add token counting:

```python
STUFF_THRESHOLD_TOKENS = 500_000  # gemini-3.6-flash context is ~1M; leave headroom for
                                   # prompt scaffolding, conversation history, and the answer

def _get_client():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not configured")
    if genai is None:
        raise RuntimeError("google-genai is not installed")
    return genai.Client(api_key=api_key)

def count_tokens(text: str, model: str = DEFAULT_MODEL) -> int:
    """Return the exact token count for text under the given model's tokenizer."""
    client = _get_client()
    result = client.models.count_tokens(model=model, contents=text)
    return result.total_tokens
```

Update `answer_question` to use `_get_client()` instead of its inline setup. Its signature and
behavior (`context: list[str]` joined and inserted into the prompt) do NOT need to change — both
the stuffed and retrieved paths already produce a `list[str]` for `context`.

## 3. `/upload` in `api/routes.py`

Pass the original extracted `text` (before `split_text()` is called) through to
`save_session_document` as the new `raw_text` argument. No other change to this endpoint.

## 4. `/ask` in `api/routes.py` — the branch

Before the existing embedding/retrieval loop:

1. Compute `total_tokens = sum(count_tokens(doc["raw_text"]) for doc in session_documents)`
2. **If `total_tokens < STUFF_THRESHOLD_TOKENS`:**
   - Skip `generate_embeddings` and `InMemoryRetriever` entirely for this request
   - Build `context = [f"[{doc['filename']}]\n{doc['raw_text']}" for doc in session_documents]`
   - Build `selected_chunks`-equivalent data for the response's `sources` field using each
     document's full `raw_text` as `SourceReference.text` (there is no chunk-level ranking to
     report when nothing was chunked — the source IS the whole document)
   - Log which path was taken, e.g. `logger.info("Stuffed %d documents directly (%d tokens, under threshold)", ...)`
3. **Else** (at or above threshold): run the existing chunked-retrieval code path completely
   unchanged (embed query, loop documents, `InMemoryRetriever.search_with_embedding`, rank, select
   top-k, build `context` from chunks)
4. Both branches converge on the same `answer_question(...)` call and the same `AskResponse`
   construction — do not duplicate that part

## Constraints

- `retriever.py` must not change at all
- `chunking.py` must not change at all
- `answer_question`'s signature must not change
- Keep the interview-explainable style: no new dependencies (token counting uses `google-genai`'s
  existing `count_tokens`, not a separate tokenizer library)

## Tests to add (pytest)

Follow existing conventions (see `test_chunking.py`, `test_auth.py`):

1. A migration test: create a `session_documents` table via the OLD schema (no `raw_text` column),
   run `init_db()`/the migration step, assert the column now exists and existing rows aren't lost
2. `save_session_document`/`get_session_documents` round-trip test asserting `raw_text` is stored
   and returned correctly
3. `/ask` test with a small mocked document set (under threshold) asserting `generate_embeddings`
   and `InMemoryRetriever` are NOT called, and the response still returns a valid answer + sources
4. `/ask` test with a mocked large document set (over threshold, e.g. mock `count_tokens` to
   return a large number) asserting the existing chunked path still runs exactly as before
5. A boundary test at exactly `STUFF_THRESHOLD_TOKENS` to confirm which side of the threshold it
   falls on (recommend: `>=` goes to retrieval, so the threshold value itself is the first
   "large" case — call this out explicitly in the implementation so it's not ambiguous)
6. Confirm `.\venv\Scripts\python.exe -m pytest` passes in full, not bare `pytest`

## Implementation notes

- Mock `count_tokens` in tests rather than hitting the real Gemini API, consistent with how
  `generate_embeddings`/`answer_question` are presumably already mocked in existing tests
- Do not touch the frontend (`app.js`, `index.html`) — this is a backend-only change; the
  `/ask` response shape (`AskResponse`) does not change
- Do not proceed to any other roadmap item (e.g. AWS Lambda deployment) — scoped to this hybrid only
