---
mode: agent
description: Fix long filenames overflowing the sidebar and hiding the three-dot menu button
---

# Fix sidebar overflow for very long filenames

Bug: a filename with no spaces and about 60+ characters pushes the document row wider than the sidebar. The row is clipped at the sidebar edge (the sidebar has `overflow-x: hidden`), so the three-dot button is not visible. The upload success message ("<filename> uploaded, ready for questions") is clipped the same way.

This is a CSS-only fix. Read `static/style.css` and `static/index.html` first. Do not change `static/app.js` or anything in `api/`.

Always run commands with the venv interpreter: `.\venv\Scripts\python.exe -m pytest`. Never use bare `python` or `pytest`.

## Step 1: Find the real cause

Truncation on `.document-name` already exists (`min-width: 0`, `overflow: hidden`, `text-overflow: ellipsis`, `white-space: nowrap`), yet the row is still too wide. So some ancestor is not allowed to shrink. Walk the element chain from `.document-name` up to the sidebar and check each level for:

1. A flex item without `min-width: 0` (flex and grid items default to `min-width: auto`, which prevents shrinking below their content width).
2. A grid container whose column is `1fr` or `auto`. Change it to `minmax(0, 1fr)`.
3. A list, row, or wrapper without `max-width: 100%` and `box-sizing: border-box`.

Fix the actual level(s) that cause it. Do not rely on `overflow-x: hidden` to hide the problem, because that is what currently clips the button.

## Step 2: Long unbroken text elsewhere in the sidebar

Apply `overflow-wrap: anywhere` (with `min-width: 0` where it sits in a flex row) to the upload success and error message, and to any other user-supplied text in the sidebar, such as session titles. These should wrap onto multiple lines, not be truncated.

## Step 3: Requirements

- The three-dot button must be fully visible and clickable at every filename length.
- Long filenames keep the ellipsis, and the full name stays available in the `title` tooltip.
- The dropdown must still open leftward and stay inside the sidebar.
- No horizontal scrollbar anywhere in the sidebar, and no visual change for short filenames.

## Finish

Run `.\venv\Scripts\python.exe -m pytest` and report the pass count. Do not commit or merge. Tell me which ancestor was causing the overflow and what you changed, so I can review it with `git diff static/style.css`. Then list the manual checks: a 60+ character filename without spaces, a 200 character one, a short one, and a long upload message.
