"""HTTP routes for document upload and question answering."""

from io import BytesIO
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
documents: dict[str, InMemoryRetriever] = {}


class UploadResponse(BaseModel):
    doc_id: str
    chunk_count: int


class AskRequest(BaseModel):
    doc_id: str
    question: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=1, le=20)
    model: str = DEFAULT_MODEL


class AskResponse(BaseModel):
    answer: str
    sources: list[str]


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
    documents[doc_id] = retriever
    logger.info("Chunking done and embeddings generated for document %s", doc_id)
    return UploadResponse(doc_id=doc_id, chunk_count=len(chunks))


@router.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest) -> AskResponse:
    """Retrieve context for a question and generate a grounded answer."""
    retriever = documents.get(request.doc_id)
    if retriever is None:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        context = retriever.search(request.question, request.top_k)
        answer = answer_question(
            request.question,
            context,
            model=request.model,
        )
    except Exception as exc:
        logger.exception("Question answering pipeline failed")
        raise HTTPException(status_code=502, detail="Could not generate an answer") from exc

    logger.info("LLM call made for document %s", request.doc_id)
    return AskResponse(answer=answer, sources=context)