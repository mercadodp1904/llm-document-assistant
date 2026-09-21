# List a session's documents (fix: documents vanish on refresh)

## Context
`session_documents` (doc_id, session_id, filename, chunks, vectors,
created_at) already exists and is correctly populated by `/upload` — see
`get_session_documents(session_id)` in `api/auth.py`, already used
internally by `/ask`.

The bug: `uploadedDocuments` in `app.js` is a client-side-only array,
populated solely by `onUploadSuccess()` after a real upload in the current
tab. There is no way for the frontend to learn what documents already
exist for a session it didn't just upload to — so refreshing the page, or
switching to a previously-used session, shows an empty document list and
leaves the ask input disabled, even though the documents are still there
server-side and `/ask` would work fine.

Fix: add a read endpoint for a session's documents, and call it whenever
a session becomes active (on initial load and on session switch).

This stays on `feature/session-switcher-ui` — it's completing milestone 3,
not a new feature.

## 1. Backend — `api/routes.py`

Add two response models near the existing `Session*Response` models:
```python
class SessionDocumentResponse(BaseModel):
    doc_id: str
    filename: str


class SessionDocumentsResponse(BaseModel):
    documents: list[SessionDocumentResponse]
```

Add the endpoint (place it near the other `/sessions` routes):
```python
@router.get("/sessions/{session_id}/documents", response_model=SessionDocumentsResponse)
async def list_session_documents(
    session_id: str,
    current_user: str = Depends(get_current_user),
) -> SessionDocumentsResponse:
    _require_owned_session(session_id, current_user)
    return SessionDocumentsResponse(
        documents=[
            SessionDocumentResponse(doc_id=row["doc_id"], filename=row["filename"])
            for row in get_session_documents(session_id)
        ]
    )
```
`get_session_documents` already returns `chunks`/`vectors` columns too —
just don't include them in the response model, no changes needed to
`api/auth.py`.

## 2. Tests — `tests/test_routes.py`

Add (using the existing `sessions_client` fixture and `_upload_document`/
`_create_session` helpers already in this file):
- `GET /sessions/{id}/documents` without a valid token → 401
- `GET /sessions/{id}/documents` for an unknown `session_id` → 404
- `GET /sessions/{id}/documents` for a session owned by another user → 403
- After uploading 2 documents to a session (mock `PdfReader` and
  `generate_embeddings` the same way `test_documents_are_isolated_between_sessions`
  does), `GET /sessions/{id}/documents` returns both, each with the
  correct `doc_id` (matching the upload response) and `filename`
- A second, empty session for the same user returns `{"documents": []}`
  (confirms isolation, mirroring `test_documents_are_isolated_between_sessions`)

## 3. Frontend — `static/app.js`

### Extract a shared enable/disable helper
Currently the ask input's enabled state is decided independently in two
places (`onUploadSuccess()` and the `finally` block of
`loadConversationHistory()`), with slightly different conditions. Replace
both with a single helper:
```js
function updateAskAvailability() {
  const canAsk = conversationHistoryLoaded && uploadedDocuments.length > 0;
  questionInput.disabled = !canAsk;
  askButton.disabled = !canAsk;
}
```
- In `onUploadSuccess()`, replace the two lines that set
  `questionInput.disabled`/`askButton.disabled` with a call to
  `updateAskAvailability()`.
- In `loadConversationHistory()`'s `finally` block, replace the
  `if (uploadedDocuments.length > 0) { ... }` block with a call to
  `updateAskAvailability()`.

### New function: `loadSessionDocuments()`
```js
async function loadSessionDocuments() {
  try {
    const response = await authenticatedFetch(
      `/sessions/${encodeURIComponent(currentSessionId)}/documents`
    );
    if (!response.ok) {
      throw new Error(
        await readApiError(response, "Could not load this session's documents.")
      );
    }
    const data = await response.json();
    uploadedDocuments.length = 0;
    uploadedDocuments.push(
      ...data.documents.map((doc) => ({ docId: doc.doc_id, fileName: doc.filename }))
    );
    renderUploadedDocuments();
  } catch (error) {
    showError(error.message || "Could not load this session's documents.");
  } finally {
    updateAskAvailability();
  }
}
```

### Wire it in
Call `loadSessionDocuments()` everywhere a session becomes active — i.e.
alongside every existing call to `loadConversationHistory()`:
- In `showMainApp()`, after `await loadConversationHistory();`, add
  `await loadSessionDocuments();`
- In `selectSession()`, after `await loadConversationHistory();`, add
  `await loadSessionDocuments();`

(Sequential `await` is fine here — no need for `Promise.all`, matching
the existing style in this file.)

### Do NOT touch
- `startNewChat()` — a brand-new session correctly has zero documents;
  `resetConversationView()` already clears `uploadedDocuments` and
  `renderUploadedDocuments()` already reflects that. No fetch needed for
  a session that was just created with nothing in it.
- `uploadDocument()` / `onUploadSuccess()`'s core logic — only the two
  lines noted above change.

## Constraints
- Don't touch `api/auth.py` — `get_session_documents` already does
  everything needed.
- Don't change `/upload`, `/ask`, or their existing tests.
- Match existing naming/style conventions exactly (this file already has
  a strong established style — mirror it, don't introduce a new pattern).

## Validation
Run `.\venv\Scripts\python.exe -m pytest` and report the pass/fail count
(expect 34 + the new tests from section 2, all passing).

Then manually verify in the browser (this is the actual bug fix, so this
check matters most):
1. Log in, upload a document, ask a question.
2. Refresh the page. Confirm the document still appears in the sidebar
   list and the ask input is enabled (not just the conversation history).
3. Ask a follow-up question after refresh — confirm it works (this was
   fully broken before this fix).
4. Create a new chat, switch back to the previous session — confirm its
   documents reappear correctly, and the new (now-inactive) session's
   empty document list doesn't leak into the old one.
