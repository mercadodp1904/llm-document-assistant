---
mode: agent
description: Make /ask search across all uploaded documents (not just one), and return which document each part of the answer came from.
---

# Multi-Document Q&A with Citations

You are working in the `llm-document-assistant` repo. Current state, for context:

- `api/routes.py` stores uploaded documents in `documents: dict[str, InMemoryRetriever]`, keyed by a generated `doc_id`. Each upload creates a new entry — documents are NOT overwritten server-side.
- `AskRequest` currently requires a single `doc_id` and `/ask` only searches that one document's retriever.
- `AskResponse.sources` is currently `list[str]` — just raw chunk text, with no indication of which document a chunk came from.

The user wants two things:
1. A question should be answered using **all currently uploaded documents**, not just one.
2. The answer should come with a **reference to which document(s)** the information was drawn from.

## Required changes

### 1. Track filenames alongside retrievers

Right now only the `InMemoryRetriever` is stored per `doc_id` — there's no filename kept. Update the upload flow to store `(filename, retriever)` per `doc_id` (e.g. change the `documents` dict value to a small dataclass or `TypedDict` with `filename` and `retriever` fields) so later responses can reference documents by name, not just an opaque UUID.

### 2. Make `/ask` search across all documents

- Remove the requirement that `AskRequest.doc_id` be a single mandatory field. Decide with the existing code style whether to drop it entirely (always search everything) or make it an optional list to scope to specific documents — default to searching all currently uploaded documents when not specified.
- For each uploaded document, run retrieval (`retriever.search(...)`) to get its locally-relevant chunks.
- Combine results across documents into one global ranked list before selecting the final `top_k` chunks to pass to the LLM. Check `retriever.py` for whether `search` already returns similarity scores — if it only returns text, you'll need to expose scores so cross-document ranking is meaningful (comparing raw chunk text alone isn't enough to merge rankings fairly).
- Be mindful of cost/latency: don't naively call `generate_embeddings` per document per request if it can be avoided — reuse each document's precomputed vectors.

### 3. Return per-source document attribution

- Change `AskResponse.sources` from `list[str]` to a structured list, e.g. a list of objects containing at minimum `filename` and the chunk text (and `doc_id` if useful for the frontend to link back). Something like:
  ```python
  class SourceReference(BaseModel):
      doc_id: str
      filename: str
      text: str
  ```
- Update `AskResponse` to use `sources: list[SourceReference]` instead of `list[str]`.
- This is a breaking change to the `/ask` response contract — update the frontend's rendering of "Sources used" to display the filename(s), not just a count, once this lands. Flag this explicitly in your output so the frontend prompt work can follow up.

### 4. Prompt construction for the LLM call

- When building the prompt sent to `answer_question`, keep chunks grouped or labeled by source document (e.g. prefix each chunk with its filename) so the model has a chance to naturally reference "According to [filename]..." if it's helpful, though the primary source-of-truth for citation should be the structured `sources` field in the response, not something you rely on the model to get right in free text.

## Constraints

- Don't change how a single document's retrieval query works internally (`retriever.search`) unless required to expose scores for cross-document ranking — keep the change additive where possible.
- Keep `/upload` behavior otherwise the same — it should still return `doc_id` and `chunk_count` as before.
- After the change, state clearly: (a) what the new `/ask` request/response shape looks like, and (b) what frontend changes are now required as a follow-up (this repo has a separate `polish-frontend-ux` prompt for the upload-list UI, but it currently assumes the old single-source `sources: list[str]` shape and will need updating for this contract change).
