from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from api.main import app
from api.routes import documents


client = TestClient(app)


def _pdf_bytes(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    page.extract_text = lambda: text
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_ask_returns_answer_for_uploaded_document() -> None:
    documents["test-doc"] = type(
        "StubRetriever",
        (),
        {"search": lambda self, question, top_k: ["retrieved context"]},
    )()
    with patch("api.routes.answer_question", return_value="grounded answer"):
        response = client.post(
            "/ask",
            json={"doc_id": "test-doc", "question": "What?"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "grounded answer",
        "sources": ["retrieved context"],
    }
    documents.pop("test-doc")


def test_ask_returns_not_found_for_unknown_document() -> None:
    response = client.post(
        "/ask",
        json={"doc_id": "missing", "question": "What?"},
    )

    assert response.status_code == 404