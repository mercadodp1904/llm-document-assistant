from pathlib import Path

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
    without_token = auth_client.post("/ask", json={"question": "What?"})
    with_invalid_token = auth_client.post(
        "/ask",
        json={"question": "What?"},
        headers={"Authorization": "Bearer invalid-token"},
    )
    with_valid_token = auth_client.post(
        "/ask",
        json={"question": "What?"},
        headers={"Authorization": f"Bearer {token_response.json()['access_token']}"},
    )

    assert register_response.status_code == 201
    assert without_token.status_code == 401
    assert with_invalid_token.status_code == 401
    assert with_valid_token.status_code == 404