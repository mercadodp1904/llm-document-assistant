"""HTTP routes for document upload and question answering."""

from io import BytesIO
from dataclasses import dataclass
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from pypdf import PdfReader

from chunking import split_text
from embeddings import generate_embeddings
from llm_client import DEFAULT_MODEL, answer_question
from retriever import InMemoryRetriever
from api.auth import create_access_token, create_user, get_current_user, get_user_by_email
from api.auth import create_chat_session, get_chat_sessions, get_conversation_history
from api.auth import init_db, save_conversation_turn
from api.auth import verify_password


logger = logging.getLogger(__name__)
router = APIRouter()
init_db()


@dataclass
class StoredDocument:
    filename: str
    retriever: InMemoryRetriever


documents: dict[str, StoredDocument] = {}


class UploadResponse(BaseModel):
    doc_id: str
    chunk_count: int


class AuthRequest(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RegisterResponse(BaseModel):
    message: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class SessionCreateResponse(BaseModel):
    session_id: str
    created_at: str


class SessionResponse(BaseModel):
    session_id: str
    title: str | None
    created_at: str


class SessionsResponse(BaseModel):
    sessions: list[SessionResponse]


class HistoryTurn(BaseModel):
    question: str
    answer: str


class HistoryResponseTurn(HistoryTurn):
    created_at: str


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=1, le=20)
    model: str = DEFAULT_MODEL
    history: list[HistoryTurn] = Field(default_factory=list)


class SourceReference(BaseModel):
    doc_id: str
    filename: str
    text: str


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceReference]


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register_user(request: AuthRequest) -> RegisterResponse:
    email = request.email.strip().lower()
    try:
        create_user(email, request.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RegisterResponse(message="User registered successfully")


@router.post("/login", response_model=TokenResponse)
async def login_user(request: AuthRequest) -> TokenResponse:
    email = request.email.strip().lower()
    user = get_user_by_email(email)
    if user is None or not verify_password(request.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenResponse(access_token=create_access_token(email), token_type="bearer")


@router.post("/sessions", response_model=SessionCreateResponse)
async def create_session(
    current_user: str = Depends(get_current_user),
) -> SessionCreateResponse:
    session = create_chat_session(current_user)
    return SessionCreateResponse(
        session_id=session["session_id"],
        created_at=session["created_at"],
    )


@router.get("/sessions", response_model=SessionsResponse)
async def list_sessions(
    current_user: str = Depends(get_current_user),
) -> SessionsResponse:
    return SessionsResponse(
        sessions=[
            SessionResponse(
                session_id=session["session_id"],
                title=session["title"],
                created_at=session["created_at"],
            )
            for session in get_chat_sessions(current_user)
        ]
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    _current_user: str = Depends(get_current_user),
) -> UploadResponse:
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
async def ask_question(
    request: AskRequest,
    current_user: str = Depends(get_current_user),
) -> AskResponse:
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
        context_limit = max(request.top_k, len(documents) * request.top_k)
        selected_chunks = ranked_chunks[:context_limit]
        context = [
            f"[{filename}]\n{chunk}"
            for _, _, filename, chunk in selected_chunks
        ]
        answer = answer_question(
            request.question,
            context,
            model=request.model,
            history=[turn.model_dump() for turn in request.history[-5:]],
        )
    except Exception as exc:
        logger.exception("Question answering pipeline failed")
        raise HTTPException(status_code=502, detail="Could not generate an answer") from exc

    logger.info("LLM call made for %d uploaded documents", len(documents))
    save_conversation_turn(current_user, request.question, answer)
    sources = [
        SourceReference(doc_id=doc_id, filename=filename, text=chunk)
        for _, doc_id, filename, chunk in selected_chunks
    ]
    return AskResponse(answer=answer, sources=sources)


@router.get("/history", response_model=list[HistoryResponseTurn])
async def get_history(
    current_user: str = Depends(get_current_user),
) -> list[HistoryResponseTurn]:
    return [
        HistoryResponseTurn(
            question=row["question"],
            answer=row["answer"],
            created_at=row["created_at"],
        )
        for row in get_conversation_history(current_user)
    ]