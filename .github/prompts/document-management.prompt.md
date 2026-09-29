---
mode: agent
description: Replace-on-reupload with user notification, plus explicit delete endpoint and UI for session documents
---

# Document management: replace-on-reupload + delete

Read `api/routes.py`, `api/auth.py`, `static/app.js`, `static/index.html`, and `static/style.css` before changing anything. Keep the existing conventions: raw `sqlite3` (no ORM), vanilla JS (no frameworks or npm), narrow exception handling, and ownership checks that return 404 for a missing session and 403 for a session the user does not own.

Always run commands with the venv interpreter: `.\venv\Scripts\python.exe -m pytest` and `.\venv\Scripts\python.exe -m uvicorn`. Never use bare `python`, `pytest`, or `uvicorn`.

## Step 1: Backend, replace on re-upload

In `POST /upload` (session-scoped):

1. After extracting and chunking the file, check `session_documents` for an existing row with the same `session_id` and the same filename.
2. If one exists, delete that row and insert the new one in a single SQLite transaction, so a failure never leaves the session with zero copies or two copies.
3. Add `"replaced": true` (or `false`) to the upload response so the frontend knows what happened.
4. Do not change how chunks, vectors, or `raw_text` are stored.

## Step 2: Backend, explicit delete

1. Add `DELETE /sessions/{session_id}/documents/{document_id}`.
2. Reuse the existing ownership checks (404 if the session or document does not exist, 403 if the session belongs to another user). The document must belong to that session, otherwise 404.
3. Delete the row from `session_documents` and return 204.
4. Add a helper in `api/auth.py` next to `get_session_documents()`, for example `delete_session_document(session_id, document_id)`.

## Step 3: Frontend

In `static/app.js`, `static/index.html`, and `static/style.css`:

1. The document list already loads from the server on page load and session switch. Reuse that existing fetch-and-render code, and re-run it after an upload or delete so the list stays in sync. Do not add a new list endpoint.
2. Render a delete button next to each document. Confirm before deleting (`confirm()` is fine). On success, remove it from the list. If no documents remain, disable the ask input again.
3. After an upload, if the response has `replaced: true`, show a visible, non-blocking message such as "report.pdf was already in this chat, so the old version was replaced." Do not use `alert()`.
4. Send the bearer token on all new fetches and keep the existing 401 redirect-to-login behavior.

## Step 4: Tests

Add pytest coverage, without modifying existing tests unless a contract genuinely changed:

- Re-uploading the same filename in the same session leaves exactly one row and returns `replaced: true`.
- The same filename in a different session is not affected.
- The first upload returns `replaced: false`.
- Delete removes the document and returns 204.
- Delete returns 404 for an unknown document and 403 for another user's session.
- After delete, `/ask` on a session with no documents behaves as it did before (no crash).

## Finish

Run `.\venv\Scripts\python.exe -m pytest` and report the pass count. Do not commit or merge. Summarize what changed per file so I can review it with `git diff <file>`.
