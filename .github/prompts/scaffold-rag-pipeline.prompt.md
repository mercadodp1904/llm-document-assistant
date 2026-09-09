---
mode: agent
description: "Scaffold the initial document Q&A (RAG) pipeline"
---

Scaffold the initial version of the document Q&A tool described in
`.github/copilot-instructions.md`:

1. `chunking.py` — split extracted PDF text into overlapping chunks
   (configurable chunk size + overlap).
2. `embeddings.py` — generate embeddings for a list of text chunks.
3. `retriever.py` — given a query, embed it and return the top-k most
   similar chunks (cosine similarity, in-memory store to start).
4. `llm_client.py` — thin wrapper around the LLM API call, takes a prompt +
   retrieved context, returns an answer. Model name is a parameter with a
   sensible default, not hardcoded.
5. `api/routes.py` — FastAPI endpoints: `POST /upload` (accepts a PDF, runs
   the pipeline, stores chunks+embeddings in memory keyed by a doc id) and
   `POST /ask` (takes doc id + question, returns an answer).
6. A minimal `tests/` folder with one test per module, mocking the LLM and
   embedding calls.

Use `async def` for the upload and ask endpoints. Keep everything as simple
as possible — this is a first working version, not a final architecture.
After scaffolding, summarize the data flow end to end in plain language.
