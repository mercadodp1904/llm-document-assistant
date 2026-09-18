"""Authentication helpers backed by a small SQLite users table."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext


DATABASE_PATH = Path(__file__).resolve().parent.parent / "users.db"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


@contextmanager
def _get_connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db() -> None:
    """Create application tables when the application starts."""
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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        init_chat_sessions_table(connection)


def init_chat_sessions_table(connection: sqlite3.Connection | None = None) -> None:
    """Create the chat sessions table if it does not exist."""
    if connection is not None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT PRIMARY KEY,
                user_email TEXT NOT NULL REFERENCES users(email),
                title TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        return

    with _get_connection() as owned_connection:
        init_chat_sessions_table(owned_connection)


def create_chat_session(user_email: str) -> sqlite3.Row:
    session_id = uuid4().hex
    with _get_connection() as connection:
        connection.execute(
            """
            INSERT INTO chat_sessions (session_id, user_email, title)
            VALUES (?, ?, ?)
            """,
            (session_id, user_email, None),
        )
        session = connection.execute(
            """
            SELECT session_id, created_at
            FROM chat_sessions
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
    if session is None:
        raise RuntimeError("Could not create chat session")
    return session


def get_chat_sessions(user_email: str) -> list[sqlite3.Row]:
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT session_id, title, created_at
            FROM chat_sessions
            WHERE user_email = ?
            ORDER BY created_at DESC, session_id DESC
            """,
            (user_email,),
        ).fetchall()
    return list(rows)


def save_conversation_turn(user_email: str, question: str, answer: str) -> None:
    with _get_connection() as connection:
        connection.execute(
            """
            INSERT INTO conversation_turns (user_email, question, answer)
            VALUES (?, ?, ?)
            """,
            (user_email, question, answer),
        )


def get_conversation_history(user_email: str, limit: int = 20) -> list[sqlite3.Row]:
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT question, answer, created_at
            FROM conversation_turns
            WHERE user_email = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_email, limit),
        ).fetchall()
    return list(reversed(rows))


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