---
mode: agent
description: "Add JWT-based login/auth to the FastAPI app"
---

Add JWT-based authentication to this FastAPI project:

- A `/register` endpoint (email + password, hash password with bcrypt/passlib).
- A `/login` endpoint that returns a JWT access token on valid credentials.
- A dependency (`get_current_user`) that protects other routes by requiring
  a valid bearer token.
- Store users in whatever the project's current storage is (SQLite is fine
  if nothing else exists yet — create a minimal `users` table/model).
- Add pytest tests covering: successful register, duplicate register,
  successful login, login with wrong password, and access to a protected
  route with/without a valid token.
- Keep the JWT secret in an environment variable, never hardcoded.

After implementing, summarize in 3-4 sentences how the auth flow works, so
it can be explained in an interview.
