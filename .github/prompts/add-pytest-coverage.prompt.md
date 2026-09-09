---
mode: agent
description: "Backfill pytest tests for an existing module"
---

Review the current file/module in context and add pytest test coverage for
it:

- Mock any external calls (LLM API, file system, network).
- Cover the main success path plus at least one failure/edge case.
- Use fixtures for any repeated setup (e.g. a sample PDF, a fake API
  response).
- Name the test file `test_<module_name>.py` if it doesn't already exist,
  placed under `tests/`.
- Do not modify the implementation code unless a test reveals an actual bug
  — if it does, point it out and ask before fixing it.

After adding tests, list what is now covered and one thing that's still
untested, so it's clear what to mention (and what to caveat) in an
interview if asked "do you have tests for this?".
