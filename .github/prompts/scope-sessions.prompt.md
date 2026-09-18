# Scope conversation history and documents by chat session

## Context
`chat_sessions` (session_id, user_email, title, created_at) already exists
in `api/auth.py`, with `POST /sessions` and `GET /sessions` in
`api/routes.py` (merged to main).

Currently:
- `conversation_turns` is scoped by `user_email` only.
- `documents` is a module-level `dict[str, StoredDocument]` in
  `api/routes.py`, where `StoredDocument` is a dataclass holding
  `filename: str` and `retriever: InMemoryRetriever`. It is global,
  in-memory, and not scoped to any user or session.

Make both scoped by `session_id`, so each chat session has its own
independent history and its own independent set of uploaded documents.

## 1. `api/auth.py` changes

### Schema
Change the `conversation_turns` table definition inside `init_db()` to:

```python
CREATE TABLE IF NOT EXISTS conversation_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES chat_sessions(session_id),
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
```

This is a dev/portfolio project with no production data — change the
`CREATE TABLE` statement directly rather than writing an `ALTER TABLE`
migration.

Add a new `session_documents` table, following the same
`init_chat_sessions_table(connection=None)` pattern already used (i.e.
accepts an optional connection so it can be called both from `init_db()`
and standalone):

```python
CREATE TABLE IF NOT EXISTS session_documents (
    doc_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES chat_sessions(session_id),
    filename TEXT NOT NULL,
    chunks TEXT NOT NULL,      -- JSON-encoded list[str]
    vectors TEXT NOT NULL,     -- JSON-encoded list[list[float]]
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
```

Store `chunks` and `vectors` as `json.dumps(...)` — vectors are already
computed at upload time (via `generate_embeddings`), so there is no need
to re-embed on read. Reconstruct `InMemoryRetriever(chunks, vectors,
generate_embeddings)` when loading a document back for `/ask`.

### New functions in `api/auth.py`
- `get_chat_session(session_id: str) -> sqlite3.Row | None` — returns the
  full `chat_sessions` row (including `user_email`) for ownership checks,
  or `None` if it doesn't exist.
- `save_conversation_turn(user_email: str, session_id: str, question: str,
  answer: str) -> None` — add `session_id` as the second parameter,
  inserted into the new column. **This changes an existing function's
  signature** — every existing caller must be updated (see test section
  below).
- `get_conversation_history(session_id: str, limit: int = 20) ->
  list[sqlite3.Row]` — change from filtering by `user_email` to filtering
  by `session_id` only (ownership of the session is checked once at the
  route level via `get_chat_session`, not re-checked per-row here).
- `save_session_document(session_id: str, filename: str, chunks:
  list[str], vectors: list[list[float]]) -> str` — inserts a row with a
  new `uuid4().hex` doc_id, returns the doc_id.
- `get_session_documents(session_id: str) -> list[sqlite3.Row]` — returns
  all `session_documents` rows for that session (doc_id, filename, chunks,
  vectors as stored, i.e. still JSON strings — deserialize in
  `api/routes.py`, not in `api/auth.py`, to keep `auth.py` free of
  retriever/embedding concerns).

## 2. `api/routes.py` changes

### Remove
- The module-level `documents: dict[str, StoredDocument] = {}` and the
  `StoredDocument` dataclass's use as in-memory storage. You can keep
  `StoredDocument` as a lightweight dataclass if useful for passing data
  around within a single request, but nothing should persist in it across
  requests.

### Add a shared ownership-check helper
```python
def _require_owned_session(session_id: str, current_user: str) -> None:
    session = get_chat_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["user_email"] != current_user:
        raise HTTPException(status_code=403, detail="Session does not belong to this user")
```
Call this at the top of `/upload`, `/ask`, and `/history` (after auth,
before touching any session data).

### `/upload`
- Add `session_id: str` — since this endpoint currently takes
  `UploadFile` via `File(...)` (multipart form), add `session_id` as an
  additional `Form(...)` field (do NOT switch the whole endpoint to JSON
  body — keep the file upload mechanism as-is).
- After generating `chunks` and `vectors` (unchanged pipeline), call
  `_require_owned_session(session_id, _current_user)`, then
  `save_session_document(session_id, filename, chunks, vectors)` instead
  of writing to the `documents` dict.

### `/ask`
- Add `session_id: str` to `AskRequest` (it's already a JSON body model,
  so this is a normal added field, `session_id: str = Field(min_length=1)`).
- Call `_require_owned_session(request.session_id, current_user)` first.
- Replace the `if not documents:` check with: load
  `get_session_documents(request.session_id)`; if empty, raise 404
  "Document not found" (same message/status as today).
- Replace the loop over the global `documents.items()` with a loop over
  the loaded rows, deserializing `chunks`/`vectors` with `json.loads` and
  reconstructing `InMemoryRetriever(chunks, vectors, generate_embeddings)`
  per document, then calling `.search_with_embedding(...)` exactly as
  today.
- `save_conversation_turn(current_user, request.session_id, request.question, answer)`
  — update this call site for the new signature.

### `/history`
- Add `session_id: str` as a query parameter (this endpoint currently
  takes no body/params other than auth, so add it as
  `session_id: str = Query(...)`).
- Call `_require_owned_session(session_id, current_user)`.
- Call `get_conversation_history(session_id)` instead of
  `get_conversation_history(current_user)`.

## 3. Test updates in `tests/test_routes.py`

These existing tests manipulate the global `documents` dict directly and
must be rewritten to go through real endpoints instead, since that dict
no longer exists:

- `test_ask_returns_answer_for_uploaded_document`
- `test_ask_ranks_chunks_across_all_documents`
- `test_ask_passes_only_the_last_five_history_turns`
- `test_ask_keeps_relevant_chunks_from_all_uploaded_documents`
- `test_ask_returns_not_found_for_unknown_document`

For each: create a session first via `POST /sessions` (using the existing
`AUTH_HEADERS` / `test@example.com` user), then use the returned
`session_id` both when uploading (via real `POST /upload` calls, not by
constructing `StoredDocument` directly — `test_ask_ranks_chunks_...` and
`test_ask_passes_only_...` currently build `InMemoryRetriever` objects
by hand with hardcoded vectors, so for those, upload via `/upload` with
`generate_embeddings` mocked to return the desired fixed vectors, same
technique already used in `test_ask_keeps_relevant_chunks_from_all_uploaded_documents`)
and when calling `/ask`. Remove the `documents.pop(...)` /
`documents.clear()` cleanup — no longer needed since data is now
per-session in a temp DB, but note whether these tests need the
`history_client`-style fixture (temp `DATABASE_PATH`) to avoid leaking
sessions into the shared `users.db` used by the bare module-level
`client`. Prefer converting these to use a temp-DB fixture rather than
the shared `client`.

These tests call `auth.save_conversation_turn` directly with the old
3-argument signature and must be updated to pass a `session_id` (create
one via `create_chat_session` or through the `/sessions` endpoint first):

- `test_history_only_returns_calling_users_turns`
- `test_history_returns_only_the_20_most_recent_turns`

Also update `test_successful_ask_appears_in_history` (already uses
`history_client` and manipulates `documents` directly — same rewrite as
above, but keep the existing `history_client` fixture since it already
uses a temp DB) and `/history` calls throughout to include `session_id`
as a query param.

Add new tests:
- `/upload` with a `session_id` that doesn't exist → 404
- `/upload` with a `session_id` belonging to a different user → 403
- `/ask` and `/history` — same 404/403 checks
- Two sessions for the same user have fully independent documents:
  uploading to session A's `/upload` does not make that document
  available when calling `/ask` against session B

## Constraints
- Keep this interview-explainable: raw `sqlite3`, `json` from the stdlib
  only — no new dependencies.
- Do NOT touch `chat_sessions`, `POST /sessions`, `GET /sessions`, or
  `app.js` — out of scope for this prompt.

## Validation
Run `.\venv\Scripts\python.exe -m pytest` and report the pass/fail count.
Flag anything where the actual `InMemoryRetriever`/`retriever.py`
interface didn't match what's assumed above (e.g. if
`search_with_embedding` or the constructor signature differs from what's
described).
