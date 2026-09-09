from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from api.main import app
from api.routes import StoredDocument, documents
from retriever import InMemoryRetriever


client = TestClient(app)


def _pdf_bytes(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    page.extract_text = lambda: text
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_ask_returns_answer_for_uploaded_document() -> None:
    retriever = InMemoryRetriever(["retrieved context"], [[1.0]], lambda _: [[1.0]])
    documents["test-doc"] = StoredDocument("report.pdf", retriever)
    try:
        with patch("api.routes.answer_question", return_value="grounded answer"):
            with patch("api.routes.generate_embeddings", return_value=[[1.0]]):
                response = client.post("/ask", json={"question": "What?"})
    finally:
        documents.pop("test-doc")

    assert response.status_code == 200
    assert response.json() == {
        "answer": "grounded answer",
        "sources": [
            {"doc_id": "test-doc", "filename": "report.pdf", "text": "retrieved context"}
        ],
    }


def test_ask_ranks_chunks_across_all_documents() -> None:
    first = InMemoryRetriever(["first context"], [[0.6, 0.8]], lambda _: [[1.0, 0.0]])
    second = InMemoryRetriever(["second context"], [[1.0, 0.0]], lambda _: [[1.0, 0.0]])
    documents.update(
        {
            "first-doc": StoredDocument("first.pdf", first),
            "second-doc": StoredDocument("second.pdf", second),
        }
    )
    try:
        with patch("api.routes.answer_question", return_value="combined answer") as answer:
            with patch("api.routes.generate_embeddings", return_value=[[1.0, 0.0]]):
                response = client.post("/ask", json={"question": "What?", "top_k": 2})
    finally:
        documents.pop("first-doc")
        documents.pop("second-doc")

    assert response.status_code == 200
    assert [source["filename"] for source in response.json()["sources"]] == [
        "second.pdf",
        "first.pdf",
    ]
    assert answer.call_args.args[1] == [
        "[second.pdf]\nsecond context",
        "[first.pdf]\nfirst context",
    ]


def test_ask_returns_not_found_for_unknown_document() -> None:
    response = client.post(
        "/ask",
        json={"question": "What?"},
    )

    assert response.status_code == 404


def test_static_frontend_is_served() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Document Assistant" in response.text
    assert client.get("/app.js").status_code == 200