---
mode: agent
description: "Add login/register UI to the vanilla JS frontend, wired to existing JWT auth endpoints"
---

Add a frontend authentication UI to this vanilla HTML/CSS/JS app, using the
existing `/register` and `/login` endpoints (see api/routes.py and
api/auth.py):

- A login/register screen shown when there is no valid token in
  `sessionStorage`. Include a way to toggle between login and register forms.
- On successful login, store the returned `access_token` in
  `sessionStorage` and show the existing sidebar + chat interface.
- On successful register, either log the user in automatically or prompt
  them to log in — pick whichever is simpler to implement cleanly.
- Attach `Authorization: Bearer <token>` to every existing fetch call to
  `/upload` and `/ask`.
- Add a "Logout" control fixed to the bottom of the sidebar that clears the
  token from `sessionStorage` and returns to the login screen.
- If any `/upload` or `/ask` request returns 401 (e.g. expired token),
  clear the stored token and return the user to the login screen instead
  of failing silently.
- Show clear inline error messages for failed login (wrong credentials)
  and failed register (duplicate email), using the existing error message
  from the API response.
- Keep styling consistent with the existing app's CSS — don't introduce a
  new framework or build step.

After implementing, summarize in 2-3 sentences how the frontend decides
whether to show the login screen vs. the main app.