# Add chat_sessions table and session endpoints

## Context
This project (`llm-document-assistant`) currently scopes conversation history
by `user_email` only — one continuous history per user, stored in a
`conversation_turns` SQLite table (raw `sqlite3`, no ORM — see `api/auth.py`
for the existing pattern of table creation and queries).

We're introducing **chat sessions**: users should be able to have multiple
independent conversations, each with its own history and its own uploaded
documents, and switch between them or start a fresh one.

This prompt covers **only** the new `chat_sessions` table and its CRUD
endpoints. Do NOT touch `conversation_turns`, `documents`, `/history`,
`/upload`, or `/ask` in this pass — that's a separate follow-up prompt.

## Task

1. **New table** `chat_sessions` in the same SQLite database used by
   `conversation_turns` (find and reuse the existing DB connection /
   initialization pattern in `api/auth.py` — do not create a second SQLite
   file or a new connection pattern).

   Schema:
   - `session_id` — TEXT PRIMARY KEY (use `uuid4()` hex string, generated
     server-side)
   - `user_email` — TEXT NOT NULL, foreign key relationship to the existing
     users table (match however `conversation_turns.user_email` already
     references it)
   - `title` — TEXT, nullable (for now; a future prompt may auto-generate
     this from the first question asked)
   - `created_at` — TEXT or DATETIME, default to current UTC timestamp
     (match the timestamp convention already used in `conversation_turns`)

   Add an `init_chat_sessions_table()` (or equivalent, matching existing
   naming convention) function that creates the table if it doesn't exist,
   called at the same startup point where `conversation_turns` is
   initialized.

2. **`POST /sessions`** — creates a new chat session for the authenticated
   user.
   - Protected by the existing `get_current_user` dependency (same pattern
     as `/ask` and `/upload`)
   - Generates a new `session_id` (uuid4 hex), inserts a row with the
     current user's email and current timestamp, `title=None`
   - Returns `{"session_id": "...", "created_at": "..."}`

3. **`GET /sessions`** — lists all chat sessions belonging to the
   authenticated user.
   - Protected by `get_current_user`
   - Returns sessions ordered by `created_at` descending (most recent first)
   - Response shape: `{"sessions": [{"session_id": "...", "title": "...",
     "created_at": "..."}, ...]}`

## Constraints
- Keep this interview-explainable: raw `sqlite3`, no SQLAlchemy, no new
  dependencies.
- Follow the exact patterns already established in `api/auth.py` and
  `api/routes.py` for: DB connection handling, table initialization,
  Pydantic response models (if the project uses them for other endpoints —
  check first), and error handling style.
- Do not modify `conversation_turns`, `documents`, `/history`, `/upload`,
  or `/ask` — those are out of scope for this prompt.

## Tests
Add tests to the existing test suite (check `tests/test_routes.py` and
`tests/test_auth.py` for the existing style/fixtures — reuse the test
client and auth fixtures already there rather than inventing new ones):

- `POST /sessions` without a valid token returns 401
- `POST /sessions` with a valid token creates a session and returns a
  `session_id`
- `GET /sessions` without a valid token returns 401
- `GET /sessions` with a valid token returns only that user's sessions,
  ordered most-recent-first (create 2+ sessions across 2 different users
  and confirm isolation)

Run the full suite after (`.\venv\Scripts\python.exe -m pytest`) and confirm
all existing tests still pass alongside the new ones.
