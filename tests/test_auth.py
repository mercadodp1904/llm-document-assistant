from pathlib import Path
from contextlib import contextmanager
import sqlite3
from threading import Barrier, BrokenBarrierError, Thread

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


def test_session_documents_dedupe_and_index_migration_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    database_path = tmp_path / "duplicates.db"
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
            raw_text TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.executemany(
        """
        INSERT INTO session_documents (
            doc_id, session_id, filename, chunks, vectors, raw_text, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("old-doc", "session", "report.pdf", "[]", "[]", "old", "2026-01-01 00:00:00"),
            ("new-doc", "session", "report.pdf", "[]", "[]", "new", "2026-01-02 00:00:00"),
        ],
    )
    connection.commit()
    connection.close()

    with caplog.at_level("INFO", logger="api.auth"):
        auth.init_db()
    auth.init_db()

    with sqlite3.connect(database_path) as migrated_connection:
        row = migrated_connection.execute(
            "SELECT doc_id, raw_text FROM session_documents"
        ).fetchone()
        indexes = migrated_connection.execute(
            "PRAGMA index_list(session_documents)"
        ).fetchall()

    assert row == ("new-doc", "new")
    assert any(
        index[1] == "ux_session_documents_session_filename" for index in indexes
    )
    assert "Removed 1 duplicate session document rows" in caplog.text


def test_session_documents_unique_index_rejects_raw_duplicate_insert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "unique.db"
    monkeypatch.setattr(auth, "DATABASE_PATH", database_path)
    auth.init_db()
    auth.save_session_document("session", "report.pdf", ["chunk"], [[1.0]], "text")

    with sqlite3.connect(database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO session_documents (
                    doc_id, session_id, filename, chunks, vectors, raw_text
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("duplicate-doc", "session", "report.pdf", "[]", "[]", "text"),
            )


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


def test_replace_session_document_does_not_create_duplicate_rows_under_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth, "DATABASE_PATH", tmp_path / "race.db")
    auth.init_db()
    lookup_barrier = Barrier(2, timeout=5)
    original_get_connection = auth._get_connection

    @contextmanager
    def paused_get_connection():
        with original_get_connection() as connection:
            class ConnectionProxy:
                barrier_waited = False

                def execute(self, sql: str, parameters: tuple[object, ...] = ()):
                    if (
                        not self.barrier_waited
                        and ("BEGIN IMMEDIATE" in sql or "SELECT doc_id" in sql)
                    ):
                        self.barrier_waited = True
                        try:
                            lookup_barrier.wait()
                        except BrokenBarrierError:
                            pass
                    return connection.execute(sql, parameters)

            yield ConnectionProxy()

    monkeypatch.setattr(auth, "_get_connection", paused_get_connection)
    errors: list[BaseException] = []

    def replace_document(raw_text: str) -> None:
        try:
            auth.replace_session_document(
                "session",
                "report.pdf",
                [raw_text],
                [[1.0]],
                raw_text,
            )
        except BaseException as exc:
            errors.append(exc)

    threads = [
        Thread(target=replace_document, args=("first",)),
        Thread(target=replace_document, args=("second",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    rows = auth.get_session_documents("session")

    assert len(rows) == 1