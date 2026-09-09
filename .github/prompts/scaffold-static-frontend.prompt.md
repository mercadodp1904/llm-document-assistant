---
mode: agent
description: Scaffold a plain HTML/CSS/JS frontend for the LLM Document Assistant, served as static files from FastAPI.
---

# Task
Create a minimal, dependency-free frontend for this project and wire it up
to the existing FastAPI backend.

## UX flow (important — follow this exactly)
This is a two-step flow, not two independent forms:

1. **Step 1 — Upload.** User selects/drops a PDF and uploads it.
2. **Step 2 — Ask.** The question input is disabled (or hidden) until a
   document has been successfully uploaded. Once upload succeeds, show a
   persistent confirmation (e.g. "✓ filename.pdf uploaded — ready for
   questions") that stays visible — do not let it disappear after a
   moment like a toast. Then enable the question input.
3. When the user asks a question, show the user's question text above the
   returned answer (like a two-message chat exchange), not just the
   answer alone.
4. Each new question **replaces** the previous question/answer pair in
   the display — do not accumulate a running history yet. (History is a
   deliberately separate, later phase — do not build any array/list of
   past questions now.)
5. Do not build any multi-document selection UI — assume a single
   uploaded document for now. (Also a separate, later phase.)

## Requirements

1. Create a top-level `static/` folder with:
   - `index.html` — a single page with:
     - a file upload form/input for a PDF document, with an associated
       `<label>` for accessibility
     - a text input (with `<label>`) + submit button for asking a
       question, disabled until upload succeeds
     - an area to display the current question + its answer
     - a simple status/loading indicator during upload and while waiting
       for an answer
   - `style.css` — clean, minimal styling. No CSS framework.
   - `app.js` — plain vanilla JS (no build step, no bundler, no
     `import`/`export` unless served as native ES modules). Organize into
     named functions, e.g.:
     - `uploadDocument()` — POSTs the selected PDF to the upload endpoint,
       validates it's a PDF and under a reasonable size (e.g. 20MB)
       before sending
     - `onUploadSuccess()` — shows the persistent confirmation state and
       enables the question input
     - `askQuestion()` — POSTs the question to the Q&A endpoint
     - `renderExchange()` — renders the current question + its answer
       together (and any citations/sources if the API returns them),
       replacing whatever was shown before
     - `setStatus()` / `showError()` — for loading and error states

2. Mount the `static/` folder in the FastAPI app using `StaticFiles`, so
   `index.html` is served at `/` and its assets resolve correctly.

3. Frontend JS should call whatever upload/query endpoints already exist
   in `api/routes.py` — do not invent new endpoint names without checking
   the existing routes first. If JWT auth is required for these endpoints,
   handle the token (e.g. store in memory or a simple login step) rather
   than skipping auth in the frontend.

4. Handle basic error states in the UI (failed upload, non-PDF file,
   oversized file, empty question, API error response) — don't let
   failures fail silently.

5. Add at least one pytest test confirming the static files are served
   correctly (e.g. `GET /` returns 200 and the FastAPI app has the
   `StaticFiles` mount configured).

## Constraints (see copilot-instructions.md)
- No frontend framework, no npm/node build step.
- No CSS framework — plain CSS only.
- No question history, no multi-document support — explicitly out of
  scope for this pass (see UX flow above).
- Keep it simple enough to explain confidently line-by-line in an
  interview.
