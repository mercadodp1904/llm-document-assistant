---
mode: agent
description: Fix markdown rendering, contain long answers in a scrollable box, and support multiple uploaded documents in the Document Q&A frontend.
---

# Polish Frontend UX

You are working in the `llm-document-assistant` repo, on the vanilla HTML/CSS/JS frontend (`index.html`, `app.js`, `style.css`) that talks to the FastAPI backend (`/upload`, `/ask`).

Fix the following three issues. Treat them as separate, testable changes — don't couple them together in one giant diff.

## 1. Render markdown in the answer output

The `/ask` response text is inserted as raw text/innerText, so markdown syntax like `**bold**`, `### headers`, and `* bullet` lists shows up literally instead of being formatted.

- Add a lightweight markdown-to-HTML step before inserting the answer into the DOM. Prefer a small dependency-free approach (a minimal regex-based converter, or a CDN-loaded library like `marked.js` if that's acceptable for this project) — check `requirements.txt`/existing `<script>` tags first to see what's already available before adding a new dependency.
- At minimum support: bold (`**text**`), headers (`#`/`##`/`###`), unordered lists (`*`/`-`), and paragraph breaks.
- Sanitize the output (don't blindly trust `innerHTML` from LLM output) — escape any raw HTML before running it through the markdown converter to avoid injecting arbitrary markup.

## 2. Contain long answers in a scrollable box

Right now a long answer pushes the whole page down, forcing the user to scroll past the entire page to read it.

- Give the answer container a `max-height` (e.g. `400px`–`500px`, use your judgment based on the existing layout) and `overflow-y: auto` in `style.css`, so the answer scrolls within its own box instead of expanding the page.
- Keep the rest of the page (question input, upload section) fixed in place above/around it.
- Make sure this doesn't clip short answers awkwardly — the box should only scroll when content actually overflows.

## 3. Show currently uploaded documents in the UI

Note: the backend already stores each uploaded document separately (keyed by `doc_id`) — uploading a second PDF does not actually delete the first one server-side. The "replacement" the user observed is a frontend bug: the UI only tracks and displays one `doc_id`, so it looks like the old document is gone.

- Change the frontend to track a list of uploaded documents (id + filename), not a single variable.
- Show all currently uploaded documents in the UI (a simple list is fine), so it's clear multiple documents are retained.
- This only needs frontend changes for now — the underlying multi-document querying/citation behavior is handled by a separate prompt (`multi-doc-qa-with-citations`). Don't change the `/ask` request contract here.

## Constraints

- Don't introduce a frontend framework (React, Vue, etc.) — this stays vanilla JS/HTML/CSS.
- Don't change the `/ask` or `/upload` request/response contracts unless task 3 requires it — if it does, update both frontend and backend together and note the contract change explicitly.
- After each fix, briefly state how to manually verify it (e.g. "ask a question that returns a `###` header and confirm it renders as a heading, not literal `###`").
