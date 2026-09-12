from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from api.main import app
from api.auth import create_access_token
from api.routes import StoredDocument, documents
from retriever import InMemoryRetriever


client = TestClient(app)
AUTH_HEADERS = {"Authorization": f"Bearer {create_access_token('test@example.com')}"}


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
                response = client.post(
                    "/ask", json={"question": "What?"}, headers=AUTH_HEADERS
                )
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
                response = client.post(
                    "/ask",
                    json={"question": "What?", "top_k": 2},
                    headers=AUTH_HEADERS,
                )
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


def test_ask_passes_only_the_last_five_history_turns() -> None:
    retriever = InMemoryRetriever(["retrieved context"], [[1.0]], lambda _: [[1.0]])
    documents["history-doc"] = StoredDocument("report.pdf", retriever)
    history = [
        {"question": f"Question {index}", "answer": f"Answer {index}"}
        for index in range(6)
    ]
    try:
        with patch("api.routes.answer_question", return_value="answer") as answer:
            with patch("api.routes.generate_embeddings", return_value=[[1.0]]):
                response = client.post(
                    "/ask",
                    json={"question": "Follow-up?", "history": history},
                    headers=AUTH_HEADERS,
                )
    finally:
        documents.pop("history-doc")

    assert response.status_code == 200
    assert answer.call_args.kwargs["history"] == history[-5:]


def test_ask_keeps_relevant_chunks_from_all_uploaded_documents() -> None:
    class FakePage:
        def __init__(self, text: str) -> None:
            self.text = text

        def extract_text(self) -> str:
            return self.text

    class FakeReader:
        def __init__(self, text: str) -> None:
            self.pages = [FakePage(text)]

    project_text = {
        "atlas.pdf": "Project Atlas builds a document search engine.",
        "beacon.pdf": "Project Beacon monitors warehouse temperatures.",
        "cobalt.pdf": "Project Cobalt forecasts coastal flooding.",
    }

    def fake_reader(file: BytesIO) -> FakeReader:
        return FakeReader(project_text[uploaded_filename])

    uploaded_filename = ""
    try:
        with patch("api.routes.PdfReader", side_effect=fake_reader):
            with patch("api.routes.generate_embeddings", return_value=[[1.0]]):
                for uploaded_filename in project_text:
                    response = client.post(
                        "/upload",
                        files={
                            "file": (
                                uploaded_filename,
                                b"fake pdf",
                                "application/pdf",
                            )
                        },
                        headers=AUTH_HEADERS,
                    )
                    assert response.status_code == 200

                with patch("api.routes.answer_question", return_value="all projects"):
                    response = client.post(
                        "/ask",
                        json={"question": "What projects are mentioned?", "top_k": 1},
                        headers=AUTH_HEADERS,
                    )
    finally:
        documents.clear()

    assert response.status_code == 200
    assert {source["filename"] for source in response.json()["sources"]} == set(
        project_text
    )


def test_ask_returns_not_found_for_unknown_document() -> None:
    response = client.post(
        "/ask",
        json={"question": "What?"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 404


def test_static_frontend_is_served() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Document Assistant" in response.text
    assert client.get("/app.js").status_code == 200