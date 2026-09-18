"""test_routes.py"""
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from api import auth
from api.main import app
from api.auth import create_access_token


client = TestClient(app)
AUTH_HEADERS = {"Authorization": f"Bearer {create_access_token('test@example.com')}"}


@pytest.fixture
def history_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    monkeypatch.setattr(auth, "DATABASE_PATH", tmp_path / "history.db")
    auth.init_db()
    return TestClient(app)


@pytest.fixture
def sessions_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    monkeypatch.setattr(auth, "DATABASE_PATH", tmp_path / "sessions.db")
    auth.init_db()
    return TestClient(app)


def _pdf_bytes(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    page.extract_text = lambda: text
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _create_session(test_client: TestClient, headers: dict[str, str]) -> str:
    response = test_client.post("/sessions", headers=headers)
    assert response.status_code == 200
    return response.json()["session_id"]


def _upload_document(
    test_client: TestClient,
    headers: dict[str, str],
    session_id: str,
    filename: str = "report.pdf",
) -> object:
    return test_client.post(
        "/upload",
        data={"session_id": session_id},
        files={"file": (filename, b"fake pdf", "application/pdf")},
        headers=headers,
    )


class FakePage:
    def __init__(self, text: str) -> None:
        self.text = text

    def extract_text(self) -> str:
        return self.text


class FakeReader:
    def __init__(self, text: str) -> None:
        self.pages = [FakePage(text)]


def test_ask_returns_answer_for_uploaded_document(history_client: TestClient) -> None:
    session_id = _create_session(history_client, AUTH_HEADERS)
    with patch("api.routes.PdfReader", return_value=FakeReader("context")):
        with patch("api.routes.answer_question", return_value="grounded answer"):
            with patch("api.routes.generate_embeddings", return_value=[[1.0]]):
                upload_response = _upload_document(
                    history_client, AUTH_HEADERS, session_id
                )
                response = history_client.post(
                    "/ask",
                    json={"session_id": session_id, "question": "What?"},
                    headers=AUTH_HEADERS,
                )

    assert upload_response.status_code == 200
    assert response.status_code == 200
    assert response.json() == {
        "answer": "grounded answer",
        "sources": [
            {
                "doc_id": upload_response.json()["doc_id"],
                "filename": "report.pdf",
                "text": "context",
            }
        ],
    }


def test_create_session_requires_authentication(sessions_client: TestClient) -> None:
    response = sessions_client.post("/sessions")

    assert response.status_code == 401


def test_create_session_returns_session_id(sessions_client: TestClient) -> None:
    headers = {
        "Authorization": f"Bearer {create_access_token('session@example.com')}"
    }

    response = sessions_client.post("/sessions", headers=headers)

    assert response.status_code == 200
    assert response.json()["session_id"]
    assert response.json()["created_at"]


def test_list_sessions_requires_authentication(sessions_client: TestClient) -> None:
    response = sessions_client.get("/sessions")

    assert response.status_code == 401


def test_list_sessions_is_isolated_and_ordered(
    sessions_client: TestClient,
) -> None:
    first_headers = {
        "Authorization": f"Bearer {create_access_token('first@example.com')}"
    }
    second_headers = {
        "Authorization": f"Bearer {create_access_token('second@example.com')}"
    }

    first_session = sessions_client.post("/sessions", headers=first_headers).json()
    second_session = sessions_client.post("/sessions", headers=first_headers).json()
    sessions_client.post("/sessions", headers=second_headers)

    response = sessions_client.get("/sessions", headers=first_headers)

    assert response.status_code == 200
    sessions = response.json()["sessions"]
    assert {session["session_id"] for session in sessions} == {
        first_session["session_id"],
        second_session["session_id"],
    }
    assert all(session["title"] is None for session in sessions)
    assert [session["created_at"] for session in sessions] == sorted(
        (session["created_at"] for session in sessions), reverse=True
    )


def test_successful_ask_appears_in_history(history_client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {create_access_token('history@example.com')}"}
    session_id = _create_session(history_client, headers)
    with patch("api.routes.PdfReader", return_value=FakeReader("retrieved context")):
        with patch("api.routes.answer_question", return_value="grounded answer"):
            with patch("api.routes.generate_embeddings", return_value=[[1.0]]):
                upload_response = _upload_document(history_client, headers, session_id)
                ask_response = history_client.post(
                    "/ask",
                    json={"session_id": session_id, "question": "What is this?"},
                    headers=headers,
                )
        history_response = history_client.get(
            "/history", params={"session_id": session_id}, headers=headers
        )

    assert upload_response.status_code == 200
    assert ask_response.status_code == 200
    assert history_response.status_code == 200
    history = history_response.json()
    assert len(history) == 1
    assert history[0]["question"] == "What is this?"
    assert history[0]["answer"] == "grounded answer"
    assert history[0]["created_at"]


def test_history_only_returns_calling_users_turns(history_client: TestClient) -> None:
    first_headers = {
        "Authorization": f"Bearer {create_access_token('first@example.com')}"
    }
    second_headers = {
        "Authorization": f"Bearer {create_access_token('second@example.com')}"
    }
    first_session_id = _create_session(history_client, first_headers)
    second_session_id = _create_session(history_client, second_headers)
    auth.save_conversation_turn(
        "first@example.com", first_session_id, "First question", "First answer"
    )
    auth.save_conversation_turn(
        "second@example.com", second_session_id, "Second question", "Second answer"
    )

    response = history_client.get(
        "/history",
        params={"session_id": first_session_id},
        headers=first_headers,
    )

    assert response.status_code == 200
    assert [turn["question"] for turn in response.json()] == ["First question"]


def test_history_returns_only_the_20_most_recent_turns(
    history_client: TestClient,
) -> None:
    headers = {
        "Authorization": f"Bearer {create_access_token('history@example.com')}"
    }
    session_id = _create_session(history_client, headers)
    for index in range(21):
        auth.save_conversation_turn(
            "history@example.com",
            session_id,
            f"Question {index}",
            f"Answer {index}",
        )

    response = history_client.get(
        "/history",
        params={"session_id": session_id},
        headers=headers,
    )

    assert response.status_code == 200
    assert [turn["question"] for turn in response.json()] == [
        f"Question {index}" for index in range(1, 21)
    ]


def test_history_requires_authentication(history_client: TestClient) -> None:
    response = history_client.get("/history", params={"session_id": "missing"})

    assert response.status_code == 401


def test_ask_ranks_chunks_across_all_documents(history_client: TestClient) -> None:
    session_id = _create_session(history_client, AUTH_HEADERS)
    with patch("api.routes.PdfReader", side_effect=[FakeReader("first context"), FakeReader("second context")]):
        with patch("api.routes.answer_question", return_value="combined answer") as answer:
            with patch(
                "api.routes.generate_embeddings",
                side_effect=[[[0.6, 0.8]], [[1.0, 0.0]], [[1.0, 0.0]]],
            ):
                _upload_document(history_client, AUTH_HEADERS, session_id, "first.pdf")
                _upload_document(history_client, AUTH_HEADERS, session_id, "second.pdf")
                response = history_client.post(
                    "/ask",
                    json={"session_id": session_id, "question": "What?", "top_k": 2},
                    headers=AUTH_HEADERS,
                )

    assert response.status_code == 200
    assert [source["filename"] for source in response.json()["sources"]] == [
        "second.pdf",
        "first.pdf",
    ]
    assert answer.call_args.args[1] == [
        "[second.pdf]\nsecond context",
        "[first.pdf]\nfirst context",
    ]


def test_ask_passes_only_the_last_five_history_turns(
    history_client: TestClient,
) -> None:
    session_id = _create_session(history_client, AUTH_HEADERS)
    history = [
        {"question": f"Question {index}", "answer": f"Answer {index}"}
        for index in range(6)
    ]
    with patch("api.routes.PdfReader", return_value=FakeReader("retrieved context")):
        with patch("api.routes.answer_question", return_value="answer") as answer:
            with patch("api.routes.generate_embeddings", return_value=[[1.0]]):
                _upload_document(history_client, AUTH_HEADERS, session_id)
                response = history_client.post(
                    "/ask",
                    json={
                        "session_id": session_id,
                        "question": "Follow-up?",
                        "history": history,
                    },
                    headers=AUTH_HEADERS,
                )

    assert response.status_code == 200
    assert answer.call_args.kwargs["history"] == history[-5:]


def test_ask_keeps_relevant_chunks_from_all_uploaded_documents(
    history_client: TestClient,
) -> None:
    project_text = {
        "atlas.pdf": "Project Atlas builds a document search engine.",
        "beacon.pdf": "Project Beacon monitors warehouse temperatures.",
        "cobalt.pdf": "Project Cobalt forecasts coastal flooding.",
    }

    def fake_reader(file: BytesIO) -> FakeReader:
        return FakeReader(project_text[uploaded_filename])

    session_id = _create_session(history_client, AUTH_HEADERS)
    uploaded_filename = ""
    with patch("api.routes.PdfReader", side_effect=fake_reader):
        with patch("api.routes.generate_embeddings", return_value=[[1.0]]):
            for uploaded_filename in project_text:
                response = _upload_document(
                    history_client, AUTH_HEADERS, session_id, uploaded_filename
                )
                assert response.status_code == 200

            with patch("api.routes.answer_question", return_value="all projects"):
                response = history_client.post(
                    "/ask",
                    json={
                        "session_id": session_id,
                        "question": "What projects are mentioned?",
                        "top_k": 1,
                    },
                    headers=AUTH_HEADERS,
                )

    assert response.status_code == 200
    assert {source["filename"] for source in response.json()["sources"]} == set(
        project_text
    )


def test_ask_returns_not_found_for_unknown_document(sessions_client: TestClient) -> None:
    session_id = _create_session(sessions_client, AUTH_HEADERS)
    response = sessions_client.post(
        "/ask",
        json={"session_id": session_id, "question": "What?"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 404


def test_upload_rejects_unknown_session(sessions_client: TestClient) -> None:
    response = _upload_document(sessions_client, AUTH_HEADERS, "missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"


def test_upload_rejects_session_owned_by_another_user(
    sessions_client: TestClient,
) -> None:
    owner_headers = {
        "Authorization": f"Bearer {create_access_token('owner@example.com')}"
    }
    session_id = _create_session(sessions_client, owner_headers)

    response = _upload_document(sessions_client, AUTH_HEADERS, session_id)

    assert response.status_code == 403
    assert response.json()["detail"] == "Session does not belong to this user"


def test_ask_rejects_unknown_or_foreign_session(sessions_client: TestClient) -> None:
    owner_headers = {
        "Authorization": f"Bearer {create_access_token('owner@example.com')}"
    }
    session_id = _create_session(sessions_client, owner_headers)

    unknown_response = sessions_client.post(
        "/ask",
        json={"session_id": "missing", "question": "What?"},
        headers=AUTH_HEADERS,
    )
    foreign_response = sessions_client.post(
        "/ask",
        json={"session_id": session_id, "question": "What?"},
        headers=AUTH_HEADERS,
    )

    assert unknown_response.status_code == 404
    assert foreign_response.status_code == 403


def test_history_rejects_unknown_or_foreign_session(
    sessions_client: TestClient,
) -> None:
    owner_headers = {
        "Authorization": f"Bearer {create_access_token('owner@example.com')}"
    }
    session_id = _create_session(sessions_client, owner_headers)

    unknown_response = sessions_client.get(
        "/history", params={"session_id": "missing"}, headers=AUTH_HEADERS
    )
    foreign_response = sessions_client.get(
        "/history", params={"session_id": session_id}, headers=AUTH_HEADERS
    )

    assert unknown_response.status_code == 404
    assert foreign_response.status_code == 403


def test_documents_are_isolated_between_sessions(
    sessions_client: TestClient,
) -> None:
    first_session_id = _create_session(sessions_client, AUTH_HEADERS)
    second_session_id = _create_session(sessions_client, AUTH_HEADERS)
    with patch("api.routes.PdfReader", return_value=FakeReader("session one")):
        with patch("api.routes.generate_embeddings", return_value=[[1.0]]):
            upload_response = _upload_document(
                sessions_client, AUTH_HEADERS, first_session_id
            )

    with patch("api.routes.answer_question", return_value="answer"):
        with patch("api.routes.generate_embeddings", return_value=[[1.0]]):
            first_response = sessions_client.post(
                "/ask",
                json={"session_id": first_session_id, "question": "What?"},
                headers=AUTH_HEADERS,
            )
            second_response = sessions_client.post(
                "/ask",
                json={"session_id": second_session_id, "question": "What?"},
                headers=AUTH_HEADERS,
            )

    assert upload_response.status_code == 200
    assert first_response.status_code == 200
    assert second_response.status_code == 404


def test_static_frontend_is_served() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Document Assistant" in response.text
    assert client.get("/app.js").status_code == 200