---
mode: agent
description: Frontend polish for document management: no horizontal scroll, three-dot action menu, confirm before replacing
---

# Document management polish (frontend only)

Read `static/app.js`, `static/index.html`, and `static/style.css` before changing anything. This is a frontend-only change. Do not modify `api/` or any backend behavior. Keep vanilla JS (no frameworks, no npm) and the current visual style.

Always run commands with the venv interpreter: `.\venv\Scripts\python.exe -m pytest`. Never use bare `python` or `pytest`.

## Step 1: Remove horizontal scrolling in the sidebar

Currently a long filename pushes the Delete button past the sidebar edge and creates a horizontal scrollbar.

1. Set `overflow-x: hidden` on the sidebar container.
2. Make each document row a flex container. The filename element gets `flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;` and shows the full name in a `title` attribute. The action button gets `flex-shrink: 0`.
3. Check that nothing else in the sidebar (session list items, upload status message, dropzone) can exceed the sidebar width. Long text should wrap or truncate, never scroll sideways.

## Step 2: Reusable three-dot action menu

Replace the visible Delete button on each document with a three-dot (⋯) button that opens a small dropdown.

1. Write one reusable function in `static/app.js`, for example `createActionMenu(items)`, where `items` is an array like `[{ label: "Delete", onClick: fn, danger: true }]`. It returns the button plus dropdown element. It must be generic, because the same menu will later be used for chat sessions (Rename and Delete).
2. For documents, the menu has one item: **Delete**, styled as a danger action. Keep the existing `confirm()` before the delete request.
3. Behavior:
   - Clicking the ⋯ button toggles its dropdown.
   - Only one menu is open at a time.
   - Clicking outside the menu, pressing Escape, or choosing an item closes it.
   - The button has `aria-label="Document actions"`, `aria-haspopup="menu"`, and an `aria-expanded` value that updates.
4. Position the dropdown with `position: absolute; right: 0` relative to the row, so it opens leftward and stays inside the sidebar. The sidebar has `overflow-x: hidden`, so a dropdown that extends past the edge would be clipped.
5. Style it to match the current look: small, subtle border, same font and colors, a hover state on items, and a red-ish text color for danger items.

## Step 3: Confirm before replacing

1. When the user clicks Upload PDF, compare the selected file's name to the filenames in the currently loaded document list for that session. Use the same case sensitivity the backend uses for its filename match.
2. If a match exists, call `confirm("<filename> is already in this chat. Replace it with the new upload?")`. If the user cancels, stop without sending any request and leave the selected file as it is.
3. If they confirm (or there is no match), upload as usual.
4. Keep the existing post-upload notice when the response has `replaced: true`. The server remains the source of truth, so this frontend check is only a convenience.

## Finish

Run `.\venv\Scripts\python.exe -m pytest` and report the pass count (no new backend tests are expected). Do not commit or merge. Summarize what changed per file so I can review it with `git diff <file>`. Also list the manual browser checks I should do.
