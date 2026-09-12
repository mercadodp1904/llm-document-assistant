"""Authentication helpers backed by a small SQLite users table."""

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext


DATABASE_PATH = Path(__file__).resolve().parent.parent / "users.db"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def _get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    """Create the users table when the application starts."""
    with _get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                hashed_password TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def get_user_by_email(email: str) -> sqlite3.Row | None:
    with _get_connection() as connection:
        return connection.execute(
            "SELECT id, email, hashed_password, created_at FROM users WHERE email = ?",
            (email,),
        ).fetchone()


def create_user(email: str, password: str) -> None:
    hashed_password = password_context.hash(password)
    try:
        with _get_connection() as connection:
            connection.execute(
                "INSERT INTO users (email, hashed_password) VALUES (?, ?)",
                (email, hashed_password),
            )
    except sqlite3.IntegrityError as exc:
        raise ValueError("Email is already registered") from exc


def verify_password(password: str, hashed_password: str) -> bool:
    return password_context.verify(password, hashed_password)


def _get_jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET environment variable is not configured")
    return secret


def create_access_token(email: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": email, "exp": expires_at}
    return jwt.encode(payload, _get_jwt_secret(), algorithm=ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    """Decode the bearer token and return the email in its subject claim."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    try:
        payload = jwt.decode(
            credentials.credentials,
            _get_jwt_secret(),
            algorithms=[ALGORITHM],
        )
        email = payload.get("sub")
        if not isinstance(email, str) or not email:
            raise unauthorized
    except (JWTError, RuntimeError) as exc:
        raise unauthorized from exc

    return email