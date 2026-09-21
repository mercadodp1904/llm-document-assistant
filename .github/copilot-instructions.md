# Project: LLM Document Assistant

## What this project is
A document Q&A tool: user uploads a PDF, the app chunks and embeds it, stores
vectors, and answers questions grounded in the document (RAG — Retrieval
Augmented Generation). This is a portfolio project built to demonstrate
practical LLM/RAG, backend, and cloud skills for job applications
(target: Accenture Philippines and similar SWE/data roles).

## Stack
- Language: Python 3.11+
- API framework: FastAPI
- LLM: Google Gemini API (via google-genai) — keep the LLM call behind a thin wrapper/interface so the provider can be swapped without touching business logic.
- Embeddings: sentence-transformers or the embedding endpoint of the chosen
  LLM provider.
- Vector storage: start simple (in-memory or SQLite + numpy / FAISS) — do not
  reach for a hosted vector DB unless asked.
- Auth: JWT-based, using python-jose (already implemented in `api/auth.py`).
- Frontend: plain HTML/CSS/JS, no build step, no framework (no React/Vue/
  npm toolchain unless explicitly asked). Served as static files directly
  from FastAPI. Talks to the API via `fetch()` — no server-rendered
  templates (Jinja2) unless asked.
- Testing: pytest.
- Deployment target: AWS (Lambda or a small EC2/Fargate service) — decided
  at deploy time; SQLite needs persistent disk, which not all deployment
  targets provide, so the final choice depends on the target.

## Running tests and the server
This project uses a Python virtual environment at `venv/`. The global
Python install on this machine has an unpinned `bcrypt` version that is
incompatible with `passlib`'s bcrypt backend — running Python or pytest
through the global interpreter instead of the venv causes spurious auth
test failures (`module 'bcrypt' has no attribute '__about__'`) that are
unrelated to any actual code change.

**Always use these exact commands, never the bare equivalents:**
- Run tests: `.\venv\Scripts\python.exe -m pytest`
  (NOT `pytest`, NOT `python -m pytest`)
- Run the server: `.\venv\Scripts\python.exe -m uvicorn api.main:app --reload`
  (NOT bare `uvicorn api.main:app --reload`)
- Install/update dependencies: `.\venv\Scripts\python.exe -m pip install ...`

If a task requires activating the venv in a persistent shell instead, use
`.\venv\Scripts\Activate.ps1` (preceded by `Set-ExecutionPolicy -Scope
Process -ExecutionPolicy RemoteSigned` if execution policy blocks it) and
confirm the prompt shows `(venv)` before running anything. When reporting
test results, always state which command was used to run them.

## Coding conventions
- Prefer explicit, readable code over clever one-liners — this project is
  meant to be explained confidently in interviews, so avoid patterns the
  author can't walk through line by line.
- Type hints on all function signatures.
- Keep functions small and single-purpose; one concern per module
  (e.g. `chunking.py`, `embeddings.py`, `retriever.py`, `llm_client.py`,
  `api/auth.py`, `api/routes.py`).
- SQLite access is raw `sqlite3`, no ORM. When adding a new table, follow
  the existing pattern in `api/auth.py`: an `init_<table>_table(connection
  = None)` function that accepts an optional connection (reusing one
  already open inside `init_db()`) or opens its own via `_get_connection()`
  if called standalone.
- Data that belongs to a specific user or chat session must be scoped and
  filtered in the SQL query itself (`WHERE user_email = ?` /
  `WHERE session_id = ?`), never trusted from client input alone. Ownership
  checks (404 if not found, 403 if not owned) happen once at the route
  level before touching session data.
- Frontend JS should be plain, readable vanilla JS — no jQuery, no bundler
  syntax (no `import`/`export` unless served as native ES modules). Keep
  `app.js` organized into clearly named functions (e.g. `uploadDocument()`,
  `askQuestion()`, `renderAnswer()`) since this also needs to be explained
  in interviews.
- Use `async def` for I/O-bound endpoints (file upload, LLM calls) — this is
  intentional, since explaining async/event-driven behavior is part of the
  learning goal for this project.
- Never hardcode API keys or secrets. Always load from environment variables
  via `python-dotenv` locally, and from the platform's secrets manager in
  deployment.
- Every new feature should come with at least one pytest test. Don't ask
  whether to add tests — add them. When an existing function's signature
  changes, update every call site and every test that calls it directly —
  don't leave stale callers that happen to still pass.
- Prefer standard library / small well-known packages over heavy frameworks.

## What Copilot should NOT do
- Don't suggest a hosted vector database, managed RAG platform, or paid
  SaaS wrapper. The point of this project is to demonstrate the author can
  build the RAG pipeline themselves, not glue together no-code tools.
- Don't silently swap the LLM provider or model without flagging it.
- Don't add authentication complexity beyond JWT (no OAuth providers,
  no third-party auth services) unless explicitly asked.
- Don't introduce a frontend build step, npm/node toolchain, or JS
  framework (React, Vue, etc.) unless explicitly asked. The frontend is
  intentionally plain static HTML/CSS/JS served by FastAPI.
- Don't run tests or the server with a bare `python`/`pytest`/`uvicorn`
  command — always the venv-qualified form above.

## Context for explanations
When explaining code changes in chat, keep explanations short and geared
toward someone who will need to describe this project in a technical
interview — favor "why" over "what".