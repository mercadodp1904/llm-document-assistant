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
from llm_client import STUFF_THRESHOLD_TOKENS


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


@pytest.fixture(autouse=True)
def mock_token_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("api.routes.count_tokens", lambda *args, **kwargs: 1)


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


def test_rename_session_trims_title_and_updates_session_list(
    sessions_client: TestClient,
) -> None:
    session_id = _create_session(sessions_client, AUTH_HEADERS)

    response = sessions_client.patch(
        f"/sessions/{session_id}",
        json={"title": "  Research notes  "},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Research notes"
    listed_sessions = sessions_client.get("/sessions", headers=AUTH_HEADERS).json()[
        "sessions"
    ]
    assert next(session for session in listed_sessions if session["session_id"] == session_id)[
        "title"
    ] == "Research notes"


@pytest.mark.parametrize("title", ["", "   ", "x" * 101])
def test_rename_session_rejects_invalid_title(
    sessions_client: TestClient, title: str
) -> None:
    session_id = _create_session(sessions_client, AUTH_HEADERS)

    response = sessions_client.patch(
        f"/sessions/{session_id}", json={"title": title}, headers=AUTH_HEADERS
    )

    assert response.status_code == 422


def test_rename_session_rejects_unknown_foreign_and_unauthenticated_requests(
    sessions_client: TestClient,
) -> None:
    owner_headers = {
        "Authorization": f"Bearer {create_access_token('owner@example.com')}"
    }
    session_id = _create_session(sessions_client, owner_headers)

    assert (
        sessions_client.patch(
            "/sessions/missing", json={"title": "Missing"}, headers=AUTH_HEADERS
        ).status_code
        == 404
    )
    assert (
        sessions_client.patch(
            f"/sessions/{session_id}",
            json={"title": "Foreign"},
            headers=AUTH_HEADERS,
        ).status_code
        == 403
    )
    assert (
        sessions_client.patch(f"/sessions/{session_id}", json={"title": "No auth"}).status_code
        == 401
    )


def test_delete_session_removes_only_target_session_data(
    sessions_client: TestClient,
) -> None:
    owner_session = _create_session(sessions_client, AUTH_HEADERS)
    second_session = _create_session(sessions_client, AUTH_HEADERS)
    foreign_headers = {
        "Authorization": f"Bearer {create_access_token('foreign@example.com')}"
    }
    foreign_session = _create_session(sessions_client, foreign_headers)

    auth.save_conversation_turn("test@example.com", owner_session, "owner", "answer")
    auth.save_session_document(owner_session, "owner.pdf", ["owner"], [[1.0]], "owner")
    auth.save_conversation_turn("test@example.com", second_session, "second", "answer")
    auth.save_session_document(second_session, "second.pdf", ["second"], [[1.0]], "second")
    auth.save_conversation_turn("foreign@example.com", foreign_session, "foreign", "answer")
    auth.save_session_document(foreign_session, "foreign.pdf", ["foreign"], [[1.0]], "foreign")

    response = sessions_client.delete(
        f"/sessions/{owner_session}", headers=AUTH_HEADERS
    )

    assert response.status_code == 204
    assert auth.get_chat_session(owner_session) is None
    assert auth.get_conversation_history(owner_session) == []
    assert auth.get_session_documents(owner_session) == []
    assert auth.get_conversation_history(second_session)
    assert auth.get_session_documents(second_session)
    assert auth.get_chat_session(foreign_session) is not None
    assert auth.get_conversation_history(foreign_session)
    assert auth.get_session_documents(foreign_session)
    remaining_sessions = sessions_client.get("/sessions", headers=AUTH_HEADERS).json()[
        "sessions"
    ]
    assert {session["session_id"] for session in remaining_sessions} == {second_session}


def test_delete_session_rejects_unknown_foreign_and_unauthenticated_requests(
    sessions_client: TestClient,
) -> None:
    owner_headers = {
        "Authorization": f"Bearer {create_access_token('owner@example.com')}"
    }
    session_id = _create_session(sessions_client, owner_headers)

    assert sessions_client.delete("/sessions/missing", headers=AUTH_HEADERS).status_code == 404
    assert sessions_client.delete(
        f"/sessions/{session_id}", headers=AUTH_HEADERS
    ).status_code == 403
    assert sessions_client.delete(f"/sessions/{session_id}").status_code == 401


def test_delete_session_is_not_repeatable_and_history_is_not_found(
    sessions_client: TestClient,
) -> None:
    session_id = _create_session(sessions_client, AUTH_HEADERS)

    first_response = sessions_client.delete(
        f"/sessions/{session_id}", headers=AUTH_HEADERS
    )
    second_response = sessions_client.delete(
        f"/sessions/{session_id}", headers=AUTH_HEADERS
    )
    history_response = sessions_client.get(
        "/history", params={"session_id": session_id}, headers=AUTH_HEADERS
    )

    assert first_response.status_code == 204
    assert second_response.status_code == 404
    assert history_response.status_code == 404


def test_list_session_documents_requires_authentication(
    sessions_client: TestClient,
) -> None:
    response = sessions_client.get("/sessions/missing/documents")

    assert response.status_code == 401


def test_list_session_documents_rejects_unknown_session(
    sessions_client: TestClient,
) -> None:
    response = sessions_client.get(
        "/sessions/missing/documents", headers=AUTH_HEADERS
    )

    assert response.status_code == 404


def test_list_session_documents_rejects_foreign_session(
    sessions_client: TestClient,
) -> None:
    owner_headers = {
        "Authorization": f"Bearer {create_access_token('owner@example.com')}"
    }
    session_id = _create_session(sessions_client, owner_headers)

    response = sessions_client.get(
        f"/sessions/{session_id}/documents", headers=AUTH_HEADERS
    )

    assert response.status_code == 403


def test_list_session_documents_returns_uploaded_documents(
    sessions_client: TestClient,
) -> None:
    session_id = _create_session(sessions_client, AUTH_HEADERS)
    with patch(
        "api.routes.PdfReader",
        side_effect=[FakeReader("first document"), FakeReader("second document")],
    ):
        with patch("api.routes.generate_embeddings", return_value=[[1.0]]):
            first_upload = _upload_document(
                sessions_client, AUTH_HEADERS, session_id, "first.pdf"
            )
            second_upload = _upload_document(
                sessions_client, AUTH_HEADERS, session_id, "second.pdf"
            )

    response = sessions_client.get(
        f"/sessions/{session_id}/documents", headers=AUTH_HEADERS
    )

    assert response.status_code == 200
    assert {
        document["doc_id"]: document["filename"]
        for document in response.json()["documents"]
    } == {
        first_upload.json()["doc_id"]: "first.pdf",
        second_upload.json()["doc_id"]: "second.pdf",
    }


def test_list_session_documents_returns_empty_for_empty_session(
    sessions_client: TestClient,
) -> None:
    session_id = _create_session(sessions_client, AUTH_HEADERS)

    response = sessions_client.get(
        f"/sessions/{session_id}/documents", headers=AUTH_HEADERS
    )

    assert response.status_code == 200
    assert response.json() == {"documents": []}


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
            with patch("api.routes.count_tokens", return_value=STUFF_THRESHOLD_TOKENS):
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


def test_ask_stuffs_small_documents_without_retrieval(
    history_client: TestClient,
) -> None:
    session_id = _create_session(history_client, AUTH_HEADERS)
    auth.save_session_document(
        session_id,
        "report.pdf",
        ["chunk"],
        [[1.0]],
        "The complete report text.",
    )

    with patch("api.routes.count_tokens", return_value=10):
        with patch("api.routes.generate_embeddings") as embeddings:
            with patch("api.routes.InMemoryRetriever") as retriever:
                with patch("api.routes.answer_question", return_value="answer"):
                    response = history_client.post(
                        "/ask",
                        json={"session_id": session_id, "question": "What?"},
                        headers=AUTH_HEADERS,
                    )

    assert response.status_code == 200
    source = response.json()["sources"][0]
    assert source["filename"] == "report.pdf"
    assert source["text"] == "The complete report text."
    embeddings.assert_not_called()
    retriever.assert_not_called()


@pytest.mark.parametrize(
    "token_count", [STUFF_THRESHOLD_TOKENS, STUFF_THRESHOLD_TOKENS + 1]
)
def test_ask_uses_retrieval_at_or_above_threshold(
    history_client: TestClient, token_count: int
) -> None:
    session_id = _create_session(history_client, AUTH_HEADERS)
    auth.save_session_document(
        session_id,
        "report.pdf",
        ["retrieved chunk"],
        [[1.0]],
        "The complete report text.",
    )

    with patch("api.routes.count_tokens", return_value=token_count):
        with patch("api.routes.generate_embeddings", return_value=[[1.0]]) as embeddings:
            with patch("api.routes.InMemoryRetriever") as retriever:
                retriever.return_value.search_with_embedding.return_value = [
                    (1.0, "retrieved chunk")
                ]
                with patch("api.routes.answer_question", return_value="answer"):
                    response = history_client.post(
                        "/ask",
                        json={"session_id": session_id, "question": "What?"},
                        headers=AUTH_HEADERS,
                    )

    assert response.status_code == 200
    embeddings.assert_called_once_with(["What?"])
    retriever.assert_called_once()
    assert response.json()["sources"][0]["text"] == "retrieved chunk"


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


def test_upload_replaces_existing_document_with_same_filename_in_same_session(
    sessions_client: TestClient,
) -> None:
    session_id = _create_session(sessions_client, AUTH_HEADERS)
    with patch("api.routes.PdfReader", side_effect=[FakeReader("first"), FakeReader("second")]):
        with patch("api.routes.generate_embeddings", return_value=[[1.0]]):
            first_upload = _upload_document(
                sessions_client, AUTH_HEADERS, session_id, "report.pdf"
            )
            second_upload = _upload_document(
                sessions_client, AUTH_HEADERS, session_id, "report.pdf"
            )

    rows = auth.get_session_documents(session_id)

    assert first_upload.status_code == 200
    assert first_upload.json()["replaced"] is False
    assert second_upload.status_code == 200
    assert second_upload.json()["replaced"] is True
    assert len(rows) == 1
    assert rows[0]["filename"] == "report.pdf"
    assert rows[0]["raw_text"] == "second"


def test_upload_keeps_same_filename_across_different_sessions(
    sessions_client: TestClient,
) -> None:
    first_session_id = _create_session(sessions_client, AUTH_HEADERS)
    second_session_id = _create_session(sessions_client, AUTH_HEADERS)
    with patch("api.routes.PdfReader", side_effect=[FakeReader("first"), FakeReader("second")]):
        with patch("api.routes.generate_embeddings", return_value=[[1.0]]):
            first_upload = _upload_document(
                sessions_client, AUTH_HEADERS, first_session_id, "shared.pdf"
            )
            second_upload = _upload_document(
                sessions_client, AUTH_HEADERS, second_session_id, "shared.pdf"
            )

    assert first_upload.status_code == 200
    assert first_upload.json()["replaced"] is False
    assert second_upload.status_code == 200
    assert second_upload.json()["replaced"] is False
    assert len(auth.get_session_documents(first_session_id)) == 1
    assert len(auth.get_session_documents(second_session_id)) == 1


def test_upload_rejects_unknown_session(sessions_client: TestClient) -> None:
    response = _upload_document(sessions_client, AUTH_HEADERS, "missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"


def test_delete_document_removes_document_and_returns_204(
    sessions_client: TestClient,
) -> None:
    session_id = _create_session(sessions_client, AUTH_HEADERS)
    with patch("api.routes.PdfReader", return_value=FakeReader("document text")):
        with patch("api.routes.generate_embeddings", return_value=[[1.0]]):
            upload_response = _upload_document(
                sessions_client, AUTH_HEADERS, session_id, "report.pdf"
            )

    doc_id = upload_response.json()["doc_id"]
    response = sessions_client.delete(
        f"/sessions/{session_id}/documents/{doc_id}", headers=AUTH_HEADERS
    )

    assert response.status_code == 204
    assert auth.get_session_documents(session_id) == []


def test_delete_document_returns_not_found_for_unknown_document(
    sessions_client: TestClient,
) -> None:
    session_id = _create_session(sessions_client, AUTH_HEADERS)

    response = sessions_client.delete(
        f"/sessions/{session_id}/documents/unknown-doc", headers=AUTH_HEADERS
    )

    assert response.status_code == 404


def test_delete_document_rejects_foreign_session(
    sessions_client: TestClient,
) -> None:
    owner_headers = {
        "Authorization": f"Bearer {create_access_token('owner@example.com')}"
    }
    session_id = _create_session(sessions_client, owner_headers)
    with patch("api.routes.PdfReader", return_value=FakeReader("secret text")):
        with patch("api.routes.generate_embeddings", return_value=[[1.0]]):
            upload_response = _upload_document(
                sessions_client, owner_headers, session_id, "owner.pdf"
            )

    response = sessions_client.delete(
        f"/sessions/{session_id}/documents/{upload_response.json()['doc_id']}",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 403


def test_ask_returns_not_found_after_document_delete(
    sessions_client: TestClient,
) -> None:
    session_id = _create_session(sessions_client, AUTH_HEADERS)
    with patch("api.routes.PdfReader", return_value=FakeReader("document text")):
        with patch("api.routes.generate_embeddings", return_value=[[1.0]]):
            upload_response = _upload_document(
                sessions_client, AUTH_HEADERS, session_id, "report.pdf"
            )

    doc_id = upload_response.json()["doc_id"]
    delete_response = sessions_client.delete(
        f"/sessions/{session_id}/documents/{doc_id}", headers=AUTH_HEADERS
    )
    ask_response = sessions_client.post(
        "/ask",
        json={"session_id": session_id, "question": "What?"},
        headers=AUTH_HEADERS,
    )

    assert delete_response.status_code == 204
    assert ask_response.status_code == 404
    assert ask_response.json()["detail"] == "Document not found"


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