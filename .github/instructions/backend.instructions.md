---
applyTo: "**/*.py"
---

# Python backend instructions

- Follow PEP 8. Run through `black` formatting conventions mentally when
  writing code (double quotes, trailing commas in multi-line calls).
- All FastAPI route handlers must have a Pydantic model for their
  request/response body — no raw `dict` payloads.
- Wrap external calls (LLM API, embedding calls, file I/O) in try/except and
  raise a clear `HTTPException` with a useful status code and message —
  don't let raw exceptions bubble up to the client.
- Log key pipeline steps (chunking done, embeddings generated, LLM call
  made) at INFO level using the standard `logging` module — this doubles as
  a way to explain the pipeline later.
- Any function that calls the LLM API must accept a `model` parameter with a
  sensible default, not a hardcoded model string buried in the function body.
