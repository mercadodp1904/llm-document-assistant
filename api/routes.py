"""HTTP routes for document upload and question answering."""

from io import BytesIO
from dataclasses import dataclass
import logging
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from pypdf import PdfReader

from chunking import split_text
from embeddings import generate_embeddings
from llm_client import DEFAULT_MODEL, answer_question
from retriever import InMemoryRetriever


logger = logging.getLogger(__name__)
router = APIRouter()
@dataclass
class StoredDocument:
    filename: str
    retriever: InMemoryRetriever


documents: dict[str, StoredDocument] = {}


class UploadResponse(BaseModel):
    doc_id: str
    chunk_count: int


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=1, le=20)
    model: str = DEFAULT_MODEL


class SourceReference(BaseModel):
    doc_id: str
    filename: str
    text: str


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceReference]


@router.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)) -> UploadResponse:
    """Extract, chunk, embed, and store an uploaded PDF."""
    try:
        if file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Only PDF files are supported")
        file_bytes = await file.read()
        reader = PdfReader(BytesIO(file_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        chunks = split_text(text)
        if not chunks:
            raise HTTPException(status_code=400, detail="PDF does not contain extractable text")
        vectors = generate_embeddings(chunks)
        retriever = InMemoryRetriever(chunks, vectors, generate_embeddings)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Document upload pipeline failed")
        raise HTTPException(status_code=400, detail="Could not process the PDF") from exc

    doc_id = str(uuid4())
    documents[doc_id] = StoredDocument(filename=file.filename or "uploaded.pdf", retriever=retriever)
    logger.info("Chunking done and embeddings generated for document %s", doc_id)
    return UploadResponse(doc_id=doc_id, chunk_count=len(chunks))


@router.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest) -> AskResponse:
    """Retrieve context for a question and generate a grounded answer."""
    if not documents:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        query_vectors = generate_embeddings([request.question])
        if not query_vectors:
            raise ValueError("Could not generate a query embedding")

        ranked_chunks: list[tuple[float, str, str, str]] = []
        for doc_id, document in documents.items():
            for score, chunk in document.retriever.search_with_embedding(
                query_vectors[0], request.top_k
            ):
                ranked_chunks.append((score, doc_id, document.filename, chunk))

        ranked_chunks.sort(key=lambda item: item[0], reverse=True)
        selected_chunks = ranked_chunks[: request.top_k]
        context = [
            f"[{filename}]\n{chunk}"
            for _, _, filename, chunk in selected_chunks
        ]
        answer = answer_question(
            request.question,
            context,
            model=request.model,
        )
    except Exception as exc:
        logger.exception("Question answering pipeline failed")
        raise HTTPException(status_code=502, detail="Could not generate an answer") from exc

    logger.info("LLM call made for %d uploaded documents", len(documents))
    sources = [
        SourceReference(doc_id=doc_id, filename=filename, text=chunk)
        for _, doc_id, filename, chunk in selected_chunks
    ]
    return AskResponse(answer=answer, sources=sources)