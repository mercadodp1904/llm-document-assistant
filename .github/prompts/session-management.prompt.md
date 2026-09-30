---
mode: agent
description: Add rename and delete for chat sessions (backend endpoints, tests, sidebar three-dot menu)
---

# Session management: rename and delete chat sessions

You are working on `llm-document-assistant` (FastAPI + vanilla JS + raw `sqlite3`). Document management (replace-on-reupload, document delete, three-dot menu) is already on `main`. This feature adds **rename** and **delete** for chat sessions.

I am already on the branch `feature/session-management`. Do not create branches, commit, or merge. I review with `git diff` myself.

## Ground rules

- Read the existing code first and follow its patterns exactly. Before writing anything, look at:
  - the session endpoints (`POST/GET /sessions`), the document delete endpoint, and the ownership-check helper used by `/upload`, `/ask`, `/history` in `api/routes.py`
  - the `chat_sessions`, `conversation_turns`, and `session_documents` schemas and the existing DB helper functions in `api/auth.py`
  - `createActionMenu(items)`, `closeActionMenu()`, its document call site, and the session sidebar rendering in `static/app.js`
  - the existing tests for sessions and document delete
- Keep it interview-explainable: raw `sqlite3`, vanilla JS, no new dependencies, no new abstractions beyond what is needed.
- Do not modify `chunking.py`, `retriever.py`, or `llm_client.py`.
- Run tests only with `.\venv\Scripts\python.exe -m pytest` (never bare `pytest` or `python`).
- Keep exception handling narrow; do not add broad `except Exception` blocks.

## Backend

### 1. Rename: `PATCH /sessions/{session_id}`

- Body: JSON with the new title. Use the existing title/name column of `chat_sessions` and the same field name that `GET /sessions` returns.
- Validate: strip whitespace; reject empty (after strip) and titles over 100 characters. Use the same validation style the codebase already uses (Pydantic model with a validator or constraints) so the failure is a 422.
- Duplicate titles are allowed. Do not add a uniqueness check.
- Renaming must not change the session's position in the sessions list.
- Response: the updated session in the same shape as one item from `GET /sessions`.

### 2. Delete: `DELETE /sessions/{session_id}`

- Deletes, in this order, inside a single transaction (commit once at the end, roll back if anything fails): the session's rows in `conversation_turns`, its rows in `session_documents`, then the `chat_sessions` row.
- Do not rely on `ON DELETE CASCADE` unless the code already enables `PRAGMA foreign_keys=ON` on every connection. Delete the child rows explicitly.
- If any in-memory state is keyed by session id (a cached retriever, an in-memory document list, etc.), evict it on delete. If nothing like that exists, do nothing here.
- It must only touch the target session. Other sessions of the same user and other users' data stay untouched.
- Response status and body: mirror the existing document delete endpoint.

### 3. Ownership and auth (both endpoints)

Reuse the existing ownership-check helper and `get_current_user` dependency:

- session does not exist -> 404
- session belongs to another user -> 403
- no/invalid token -> 401

After a session is deleted, `GET /history`, `/ask`, and `/upload` for that session id must return 404 through the existing checks. No extra code should be needed for that; the tests below confirm it.

### 4. DB helpers

Put the SQL in helper functions in `api/auth.py` (for example `rename_session` and `delete_session`), matching the style of the existing helpers, so `routes.py` stays thin.

## Backend tests

Add tests in the existing test files/style. Cover at least:

- Rename: success (response has new title, and `GET /sessions` reflects it); title is trimmed; empty/whitespace title -> 422; over-length title -> 422; missing session -> 404; another user's session -> 403; no token -> 401.
- Delete: success removes the session from `GET /sessions`; its conversation turns and its `session_documents` rows are gone (assert against the DB, not just the API); a second session of the same user keeps its turns and documents; another user's data is untouched; missing session -> 404; another user's session -> 403; no token -> 401; deleting the same session twice -> second call 404; `GET /history` for the deleted session -> 404.

Run the full suite and make sure everything passes before starting the frontend.

## Frontend (`static/app.js`, `static/style.css`, `static/index.html` only if needed)

### 5. Fix `createActionMenu`

- Change the signature to `createActionMenu(items, label)`. Use `label` for the button's `aria-label` instead of the hardcoded "Document actions". If `label` is omitted, fall back to "Actions".
- Update the existing document call site to pass `"Document actions"` so document behavior is unchanged.
- In the menu item click handler, call `closeActionMenu()` before `item.onClick()`, so the menu is closed before any `confirm()`/`prompt()` dialog or list re-render happens.
- After this change, confirm the document Delete menu still works exactly as before.

### 6. Session rows in the sidebar

- Add a three-dot menu to each session row using `createActionMenu(items, "Session actions")` with two items: **Rename** and **Delete** (style Delete like the existing destructive item in the document menu, if there is one).
- Clicking the three-dot button or a menu item must not trigger the row's session-switch click. Use `stopPropagation` where needed.
- Layout: the sidebar must never scroll horizontally. The session title must truncate with an ellipsis (flex child with `min-width: 0`), the three-dot button must not shrink, and the open menu must stay fully visible inside the sidebar/viewport (not clipped by the sidebar's overflow).

### 7. Rename flow

- Use `window.prompt` pre-filled with the current title (consistent with the `confirm()` used for document replace; keep it simple).
- If the user cancels, enters an empty value, or leaves the title unchanged, send no request.
- Otherwise call `PATCH /sessions/{id}` using the same authenticated fetch pattern as the other calls (bearer token, existing 401 redirect-to-login).
- On success, update the title in the client-side sessions data and re-render the list. Do not reload the chat pane, even if this is the active session.
- On failure, show the error the same way other failures are shown in this app.

### 8. Delete flow

- Ask for confirmation with `confirm()`, stating that the session's conversation and uploaded documents will be permanently deleted.
- Call `DELETE /sessions/{id}` with the same authenticated fetch pattern.
- On success:
  - If it was **not** the active session: remove it from the list and re-render only.
  - If it **was** the active session: switch to the most recent remaining session using the existing session-switch function; if none remain, use whatever the app already does for "no sessions" / "New Chat" on first load. Clear the chat pane, `uploadedDocuments`, and any stored active-session id (for example in `sessionStorage`) so nothing from the deleted session stays on screen.
- A 404 on delete means it is already gone: refresh the list and carry on without an error. A 403 or other failure: show the error and leave the list unchanged.

## Finish

1. Run `.\venv\Scripts\python.exe -m pytest` and report the pass count.
2. Give me a short summary listing each file changed and what changed in it.
3. List anything you assumed or were unsure about (for example a column name, a helper you reused, an in-memory cache you did or did not find).
4. Do not commit or merge.
