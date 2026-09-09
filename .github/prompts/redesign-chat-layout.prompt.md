---
mode: agent
description: Redesign the frontend into a compact, app-like layout — a left sidebar for document upload/list, and a scrollable chat-style main area with full question/answer history.
---

# Redesign to Sidebar + Chat Layout

You are working in `static/index.html`, `static/style.css`, and `static/app.js` in the `llm-document-assistant` repo. The current layout is a tall, landing-page-style single column: a large hero heading, then an upload panel and a Q&A panel stacked below it. This requires scrolling the whole page just to see the answer, and only shows the single latest question/answer.

Redesign it into a compact, fixed-height app shell, similar to Slack/Messenger/Claude's own chat UI:

## Layout

- A left **sidebar** (fixed width, e.g. 280–320px) containing:
  - The PDF upload control (drag/drop + browse, same validation as today: PDF only, 20MB max).
  - The list of uploaded documents (filename list, same as today).
  - Keep this panel compact — it's a persistent sidebar, not a hero section.
- A **main chat area** taking up the remaining width, containing:
  - A scrollable message history (see below).
  - A question input pinned to the bottom of the chat area, always visible without scrolling (like a real chat app), with its submit button beside it.
- Shrink or remove the current large "Ask your document." hero heading — a small app title/header bar at the top is enough (e.g. "Document Assistant" as a compact header, not giant serif type).
- The whole shell should fit within the viewport height (`height: 100vh` on the outer container), with only the chat message list scrolling internally — not the page.

## Chat history (this is a scope change from the original scaffold)

The original frontend scaffold explicitly replaced each new question/answer and kept no history. That constraint is now lifted — the user wants full history, like a real chat thread:

- Change `app.js` state from tracking a single current exchange to an array of past exchanges (e.g. `conversationHistory = [{ question, answer, sources, timestamp }, ...]`).
- Each new question/answer pair should be **appended** to the chat area, not replace what's there — render it as a new pair of chat bubbles (user message, then assistant message), not overwrite the previous ones.
- Auto-scroll the chat area to the bottom when a new message is added, so the user doesn't have to manually scroll down after asking.
- Keep the existing markdown rendering (`renderMarkdown()`) and HTML-escaping behavior for assistant messages — don't regress the injection protection that's already in place.
- Style user questions and assistant answers distinctly (e.g. different alignment, background color, or bubble shape) so it's visually clear who "said" what, similar to a real messaging app.
- The empty state ("Your question and answer will appear here") should only show before any question has been asked, not after — once there's history, always show the chat thread.

## Constraints

- No frontend framework, no build step — same vanilla HTML/CSS/JS constraints as the rest of this project.
- Keep the existing upload flow behavior (upload disabled state, question input disabled until at least one document is uploaded, error handling) — this redesign is about layout and history, not changing how upload/ask requests work.
- Update `tests/test_routes.py::test_static_frontend_is_served` if it currently asserts on hero text (e.g. `"Ask your document."`) that no longer exists after this redesign — replace the assertion with something still-accurate about the new page (e.g. the page title or a stable element).
- Keep it responsive: on narrow viewports, the sidebar can collapse above the chat area or become a toggleable panel — use your judgment, but don't let the layout break on mobile widths.
- Note in your output whether this was implemented before or after the `multi-doc-qa-with-citations` prompt. If before, the "Sources used: N" rendering per message stays as-is for now and will need a follow-up update once that prompt changes the `/ask` response shape to include filenames.
