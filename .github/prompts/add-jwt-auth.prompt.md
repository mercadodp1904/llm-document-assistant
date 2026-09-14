---
mode: agent
description: "Add JWT-based login/auth to the FastAPI app"
---

Add JWT-based authentication to this FastAPI project:

- A `/register` endpoint (email + password, hash password with bcrypt/passlib).
- A `/login` endpoint that returns a JWT access token on valid credentials.
  Access tokens should expire after 30 minutes.
- A dependency (`get_current_user`) that protects other routes by requiring
  a valid bearer token.
- Apply the `get_current_user` dependency to the existing `/ask` and
  `/upload` routes so they require authentication.
- Store users in a SQLite database (`users.db` or similar) using a minimal
  `users` table (id, email, hashed_password, created_at). Use raw `sqlite3`
  or a lightweight approach consistent with the project's "explainable
  line-by-line" philosophy — avoid introducing a full ORM like SQLAlchemy
  unless already present.
- Keep the JWT secret in an environment variable, never hardcoded. Ensure
  it's loaded via the existing `load_dotenv()` call in `main.py`, which must
  run before `api.routes` is imported.
- Add pytest tests covering: successful register, duplicate register,
  successful login, login with wrong password, and access to a protected
  route with/without a valid token.

After implementing, summarize in 3-4 sentences how the auth flow works, so
it can be explained in an interview.