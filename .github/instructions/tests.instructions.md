---
applyTo: "tests/**/*.py"
---

# Test instructions

- Use pytest, not unittest-style classes.
- Name test files `test_<module>.py` and functions `test_<behavior>`.
- Mock external calls (LLM API, embedding API) — tests must never make real
  network calls. Use `unittest.mock.patch` or `pytest-mock`.
- For each new feature added to the app, write at least:
  1. One "happy path" test.
  2. One test for a failure/edge case (empty file, malformed input, API
     error from the LLM provider).
- Prefer small, focused test functions over one large test that checks many
  things — easier to explain individually if asked about testing approach
  in an interview.
