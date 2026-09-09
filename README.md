# LLM Document Assistant

A document Q&A tool: upload a PDF, ask questions, get answers grounded in
the document using Retrieval-Augmented Generation (RAG).

Built as a hands-on project covering LLM APIs, embeddings, RAG, FastAPI,
JWT auth, async endpoints, and (eventually) AWS deployment.

## Stack
- Python 3.11+, FastAPI
- Google Gemini API for generation (swappable via `llm_client.py`)
- sentence-transformers for embeddings
- In-memory / local vector similarity search (no hosted vector DB)
- JWT auth (python-jose + passlib)
- pytest for testing

## Setup

```bash
python -m venv venv
source venv/bin/activate  # on Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # then fill in your API key
uvicorn api.main:app --reload
```

## Current pipeline

The initial RAG pipeline is available through two endpoints:

- `POST /upload` accepts a PDF, extracts its text, creates overlapping
	chunks, generates embeddings, and stores them in memory under a document ID.
- `POST /ask` embeds a question, retrieves the most similar chunks, and sends
	those chunks plus the question to Gemini for a grounded answer.

Run the tests with `python -m pytest -q`.

## Why this project
Built to close specific gaps for software engineering / data roles:
hands-on LLM integration, cloud deployment, authentication, and
event-driven (async) backend patterns.
