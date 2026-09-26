from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from api import auth
from api.main import app


@pytest.fixture
def auth_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(auth, "DATABASE_PATH", tmp_path / "users.db")
    auth.init_db()
    return TestClient(app)


def test_register_creates_user(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/register", json={"email": "user@example.com", "password": "secret"}
    )

    assert response.status_code == 201
    assert response.json() == {"message": "User registered successfully"}


def test_register_rejects_duplicate_email(auth_client: TestClient) -> None:
    payload = {"email": "user@example.com", "password": "secret"}
    auth_client.post("/register", json=payload)

    response = auth_client.post("/register", json=payload)

    assert response.status_code == 409


def test_login_returns_access_token(auth_client: TestClient) -> None:
    auth_client.post(
        "/register", json={"email": "user@example.com", "password": "secret"}
    )

    response = auth_client.post(
        "/login", json={"email": "user@example.com", "password": "secret"}
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_login_rejects_wrong_password(auth_client: TestClient) -> None:
    auth_client.post(
        "/register", json={"email": "user@example.com", "password": "secret"}
    )

    response = auth_client.post(
        "/login", json={"email": "user@example.com", "password": "wrong"}
    )

    assert response.status_code == 401


def test_protected_route_requires_valid_token(auth_client: TestClient) -> None:
    register_response = auth_client.post(
        "/register", json={"email": "user@example.com", "password": "secret"}
    )
    token_response = auth_client.post(
        "/login", json={"email": "user@example.com", "password": "secret"}
    )
    request_body = {"session_id": "missing", "question": "What?"}
    without_token = auth_client.post("/ask", json=request_body)
    with_invalid_token = auth_client.post(
        "/ask",
        json=request_body,
        headers={"Authorization": "Bearer invalid-token"},
    )
    with_valid_token = auth_client.post(
        "/ask",
        json=request_body,
        headers={"Authorization": f"Bearer {token_response.json()['access_token']}"},
    )

    assert register_response.status_code == 201
    assert without_token.status_code == 401
    assert with_invalid_token.status_code == 401
    assert with_valid_token.status_code == 404


def test_session_documents_migrate_raw_text_without_losing_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "legacy.db"
    monkeypatch.setattr(auth, "DATABASE_PATH", database_path)
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE session_documents (
            doc_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            chunks TEXT NOT NULL,
            vectors TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        INSERT INTO session_documents (doc_id, session_id, filename, chunks, vectors)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("legacy-doc", "session", "legacy.pdf", "[]", "[]"),
    )
    connection.commit()
    connection.close()

    auth.init_db()

    with sqlite3.connect(database_path) as migrated_connection:
        columns = {
            row[1]
            for row in migrated_connection.execute(
                "PRAGMA table_info(session_documents)"
            )
        }
        row = migrated_connection.execute(
            "SELECT doc_id, raw_text FROM session_documents"
        ).fetchone()

    assert "raw_text" in columns
    assert row == ("legacy-doc", "")


def test_session_document_raw_text_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth, "DATABASE_PATH", tmp_path / "round-trip.db")
    auth.init_db()

    auth.save_session_document(
        "session",
        "report.pdf",
        ["chunk"],
        [[1.0]],
        "The original extracted document text.",
    )

    document = auth.get_session_documents("session")[0]

    assert document["raw_text"] == "The original extracted document text."