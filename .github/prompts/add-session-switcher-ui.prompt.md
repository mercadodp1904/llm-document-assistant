# Add session switcher and "New Chat" to the frontend

## Context
`app.js` currently has no concept of chat sessions. The backend now
requires `session_id` on `/upload` (form field), `/ask` (JSON body field),
and `/history` (query param). This prompt wires session state into the
existing app and adds a session switcher + "New Chat" button.

Relevant existing pieces in `app.js` to build on, not replace:
- `authenticatedFetch()` — reuse for all new session-related calls.
- `uploadedDocuments` (array) / `renderUploadedDocuments()` — client-side
  only, not fetched from the backend. When switching sessions, clear and
  re-render this, since the UI can't know what's actually stored
  server-side for a session it didn't just upload to in this tab (no
  endpoint exists yet to list a session's documents — known limitation,
  out of scope here).
- `conversationHistory` (array) — holds turns for the current in-tab
  session, used to build the `history` payload sent to `/ask`. **Known
  pre-existing quirk, not in scope to fix**: `loadConversationHistory()`
  renders past turns via `renderExchange()` but never pushes them into
  `conversationHistory`. Preserve this exact behavior.
- `loadConversationHistory()`, `showMainApp()`, `resetWorkspace()`,
  `logout()`, `uploadDocument()`, `askQuestion()` — see specific changes
  below.

## 1. Markup (`index.html`)

The existing layout is a two-column CSS grid (`.app-body { grid-template-columns:
286px minmax(0, 1fr); }`) with one `<aside class="sidebar">` used for
document upload. Add the session switcher as a **new section inside that
same sidebar**, above the existing "Workspace / Your documents" heading —
do not add a new grid column or a second sidebar element.

Insert this immediately after `<aside class="sidebar">` and before the
existing `<div class="sidebar-heading">` (the one containing `<h2>Your
documents</h2>`):

```html
<div class="sidebar-heading">
  <p class="eyebrow">Chats</p>
  <h2>Your sessions</h2>
</div>
<button id="new-chat-button" class="button button-primary" type="button">+ New chat</button>
<ul id="session-list" class="session-list"></ul>
```

## 2. CSS (`style.css`)

Add a new rule block (place it near `.uploaded-documents` / `.sidebar-note`,
following the same conventions already used there):

```css
.session-list {
  list-style: none;
  margin: 14px 0 22px;
  padding: 0;
}

.session-list li {
  align-items: center;
  cursor: pointer;
  display: flex;
  font: 0.8rem/1.4 Arial, sans-serif;
  gap: 8px;
  overflow-wrap: anywhere;
  padding: 8px 6px;
}

.session-list li::before {
  background: var(--line);
  content: "";
  display: block;
  flex: 0 0 6px;
  height: 6px;
}

.session-list li:hover {
  background: var(--soft-accent);
}

.session-list li.active {
  background: var(--soft-accent);
}

.session-list li.active::before {
  background: var(--accent);
}
```

## 3. `app.js` — new state and DOM refs

Add alongside the existing `const`/`let` declarations at the top:
```js
let currentSessionId = null;
const sessions = [];
```
Add alongside the other `document.querySelector(...)` refs:
```js
const sessionListElement = document.querySelector("#session-list");
const newChatButton = document.querySelector("#new-chat-button");
```

## 4. `loadSessions()` — new function
```js
async function loadSessions() {
  const response = await authenticatedFetch("/sessions");
  if (!response.ok) {
    throw new Error(await readApiError(response, "Could not load chat sessions."));
  }
  const data = await response.json();
  sessions.length = 0;
  sessions.push(...data.sessions);
}
```

## 5. `createSession()` — new function
```js
async function createSession() {
  const response = await authenticatedFetch("/sessions", { method: "POST" });
  if (!response.ok) {
    throw new Error(await readApiError(response, "Could not start a new chat."));
  }
  return response.json();
}
```

## 6. `renderSessionList()` — new function
Renders `sessions` into `#session-list` as `<li>` elements. Use `title`
if present, otherwise fall back to a label built from `created_at`, e.g.:
```js
function sessionLabel(session) {
  return session.title || `Chat from ${new Date(session.created_at).toLocaleString()}`;
}
```
Each `<li>` gets class `active` when its `session_id` matches
`currentSessionId` (matches the CSS above). Each item's click handler
calls `selectSession(session.session_id)`.

## 7. Shared reset helper
Factor the "reset the conversation view" logic (currently inline in
`resetWorkspace()`) into a small shared function, since both
`resetWorkspace()` and the new `selectSession()` need it:
```js
function resetConversationView() {
  uploadedDocuments.length = 0;
  conversationHistory.length = 0;
  conversationHistoryLoaded = false;
  renderUploadedDocuments();
  uploadConfirmation.hidden = true;
  exchangeElement.innerHTML = `<div class="empty-state"><span class="empty-icon" aria-hidden="true">?</span><h2>What would you like to know?</h2><p>Upload a PDF, then ask a question to start a conversation.</p></div>`;
  questionInput.value = "";
  questionInput.disabled = true;
  askButton.disabled = true;
}
```
Update `resetWorkspace()` to call this instead of duplicating the logic
inline, and additionally clear session state there:
```js
sessions.length = 0;
currentSessionId = null;
sessionListElement.replaceChildren();
```

## 8. `selectSession(sessionId)` — new function
```js
async function selectSession(sessionId) {
  currentSessionId = sessionId;
  renderSessionList();
  resetConversationView();
  await loadConversationHistory();
}
```

## 9. `startNewChat()` — new function, wired to `#new-chat-button` click
```js
async function startNewChat() {
  newChatButton.disabled = true;
  try {
    const session = await createSession();
    sessions.unshift(session);
    await selectSession(session.session_id);
  } catch (error) {
    showError(error.message || "Could not start a new chat.");
  } finally {
    newChatButton.disabled = false;
  }
}
```
Note `createSession()`'s response only has `session_id`/`created_at`, no
`title` — `sessionLabel()` (step 6) already handles `title` being
undefined via `||`.

## 10. Update `showMainApp()`
After `authScreen.hidden = true; shell.hidden = false;`, replace the
existing `conversationHistoryLoaded = false; loadConversationHistory();`
with:
```js
try {
  await loadSessions();
  if (sessions.length === 0) {
    sessions.push(await createSession());
  }
  currentSessionId = sessions[0].session_id;
  renderSessionList();
  resetConversationView();
  await loadConversationHistory();
} catch (error) {
  showError(error.message || "Could not load your chats.");
}
```
(`showMainApp()` becomes `async`; update its one call site, inside
`submitAuthForm()`, to `await showMainApp()`, and the `if (getToken())`
block at the bottom of the file similarly if it isn't already inside an
async context.)

## 11. Update `loadConversationHistory()`
Change the fetch line to:
```js
const response = await authenticatedFetch(`/history?session_id=${encodeURIComponent(currentSessionId)}`);
```
No other changes to this function.

## 12. Update `uploadDocument()`
After `formData.append("file", file);`, add:
```js
formData.append("session_id", currentSessionId);
```
At the top of the function (after the existing file-presence check),
add the defensive guard:
```js
if (!currentSessionId) {
  showError("Select or start a chat first.");
  return;
}
```

## 13. Update `askQuestion()`
In the `JSON.stringify({...})` call, add `session_id: currentSessionId`
alongside `question` and `history`. Add the same defensive guard as
step 12 at the top of the function.

## 14. Wire the new button
Near the other `addEventListener` calls at the bottom of the file:
```js
newChatButton.addEventListener("click", startNewChat);
```

## 15. Error handling for 404/403
No special handling needed — `readApiError()` already reads the `detail`
field from the response, which the backend returns for both the
session-not-found (404) and session-not-owned (403) cases, and the
existing `showError()` call in each function already surfaces it.

## Constraints
- Vanilla JS only, no new dependencies or build tooling.
- Don't touch `api/auth.py`, `api/routes.py`, or the test suite — backend
  is already merged to main.
- Match existing naming/style conventions in `app.js` exactly.

## Manual verification (no automated frontend tests in this project)
1. Fresh login, brand-new user → a session auto-creates, appears in the
   sidebar, empty chat shown.
2. Upload a document, ask a question → answer appears, appears in
   `/history` on refresh.
3. Click "+ New chat" → conversation and document list reset to empty;
   the previous session still appears in the sidebar, no longer marked
   `.active`.
4. Click back to the previous session → its history reloads; its
   document list is empty (known limitation, not in scope here).
5. Refresh the page mid-session → the most recent session and its history
   reload correctly (this is the original history-rendering bug's
   scenario — confirm session scoping didn't reintroduce it).

Report any place the actual repo state required deviating from the exact
code above.
