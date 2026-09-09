---
mode: agent
description: Scaffold a plain HTML/CSS/JS frontend for the LLM Document Assistant, served as static files from FastAPI.
---

# Task
Create a minimal, dependency-free frontend for this project and wire it up
to the existing FastAPI backend.

## Requirements

1. Create a top-level `static/` folder with:
   - `index.html` — a single page with:
     - a file upload form/input for a PDF document
     - a text input + submit button for asking a question
     - an area to display the answer returned by the API
     - a simple status/loading indicator during upload and while waiting
       for an answer
   - `style.css` — clean, minimal styling. No CSS framework.
   - `app.js` — plain vanilla JS (no build step, no bundler, no
     `import`/`export` unless served as native ES modules). Organize into
     named functions, e.g.:
     - `uploadDocument()` — POSTs the selected PDF to the upload endpoint
     - `askQuestion()` — POSTs the question to the Q&A endpoint
     - `renderAnswer()` — renders the response (and any citations/sources
       if the API returns them)
     - `setStatus()` / `showError()` — for loading and error states

2. Mount the `static/` folder in the FastAPI app using `StaticFiles`, so
   `index.html` is served at `/` and its assets resolve correctly.

3. Frontend JS should call whatever upload/query endpoints already exist
   in `api/routes.py` — do not invent new endpoint names without checking
   the existing routes first. If JWT auth is required for these endpoints,
   handle the token (e.g. store in memory or a simple login step) rather
   than skipping auth in the frontend.

4. Handle basic error states in the UI (failed upload, empty question,
   API error response) — don't let failures fail silently.

5. Add at least one pytest test confirming the static files are served
   correctly (e.g. `GET /` returns 200 and the FastAPI app has the
   `StaticFiles` mount configured).

## Constraints (see copilot-instructions.md)
- No frontend framework, no npm/node build step.
- No CSS framework — plain CSS only.
- Keep it simple enough to explain confidently line-by-line in an
  interview.
