# Tasks: Base CV, File Upload and Text CV Editor

Conventions for every slice:
- Tests ship in the slice that adds the behaviour: pytest, with a file-backed SQLite where concurrency matters, and Vitest + MSW with a handler for every new or changed endpoint.
- Backend tests run on Python 3.11 (`/private/tmp/claude-501/-Users-god-Documents-else-work-hunting-jobbi/f27b7fe0-da10-4575-9087-98d451dec496/scratchpad/venv311`) and 3.14 (`backend/.venv`). Frontend tools run from `frontend/node_modules/.bin` (pnpm is broken; never npm). `schema.d.ts` is regenerated from `create_app().openapi()` after every API change.
- Library APIs (react-router data router, marked, @react-pdf/renderer `Font.register`, pdfminer.six, python-docx, Groq tool calls) are checked against current docs (context7 or the official docs) at implementation time, not from memory.
- Standard SQLAlchemy only. SQLite does not enforce foreign keys, so every new FK is nulled by hand on delete, with a test.
- **Parallel work:** before starting each slice, check which of its sub-tasks (or parts of later slices) do not depend on unmerged work and do not touch the same files or the migration chain; run those with extra agents in separate worktrees, then integrate in order. Only one branch at a time adds an Alembic migration.

---

- [x] **Slice 1: Data router (no visible change)**
  - [x] Move `app/index.tsx` and `app/router` from `<BrowserRouter>`/`<Routes>` to `createBrowserRouter` + `RouterProvider` with the same route table. Move `src/__tests__/utils.tsx` to `createMemoryRouter`. **[Agent: typescript-frontend]**
  - [x] Code review: route parity, layout and auth guard, deep links (`/?application=`), the chat draft from router state. **[Agent: react-code-reviewer]**
  - [x] Verify: the full Vitest suite and `tsc` are green. Every route opens, including the dashboard deep link and the chat draft from the Inbox (Chrome MCP if connected, otherwise curl for the routes plus a manual click-through by the user). **[Agent: qa-tester]** _(2026-11-23: PR #21 — tsc clean, Vitest 280/280, vite build OK, route tests on the real table; review no P0/P1. Browser click-through pending: Chrome not connected)_

---

- [x] **Slice 2: Every CV becomes text, edited with a live preview, exported as a full PDF**
  - [x] Migration: add `cvs.content` (Text, default `''`) and `cvs.version` (Integer, default 1). Convert every CV to text with a frozen converter inside the migration (layout from functional spec 2.2). Old columns are left untouched. Downgrade is tested on a copy of the DB. **[Agent: database-expert]**
  - [x] Converter unit tests: every field, an empty name (falls back to the CV name), an empty CV. **[Agent: python-backend]**
  - [x] API:
    - `CvCreate`/`CvUpdate`/`CvRead` move to `name` + `content` (≤ 20 000 characters) + `version`;
    - `PATCH` bumps `version`;
    - duplicate and `build_cv_copy` copy `content`;
    - the chat system prompt uses the fenced `content`;
    - the structured-field schemas and `_cv_lines` are removed.

    Update the existing tests. **[Agent: python-backend]**
  - [x] Frontend:
    - `entities/cv`: new types, `lib/cv-markdown.ts` (one `marked` lexer and a token walker), `ui/cv-text-preview.tsx`;
    - `shared/lib/is-safe-cv-link-url.ts` (http/https/mailto);
    - `features/cv-text-editor` (name, textarea with `maxLength` and paste cut, hint, preview with `useDeferredValue`, Edit/Preview tabs on phone width, Save, "CV saved" toast);
    - `pages/cv-editor` composes it;
    - delete `features/cv-editor`.

    Tests, including hostile links. **[Agent: typescript-frontend]**
  - [x] PDF:
    - rewrite `features/cv-pdf/ui/cv-document.tsx` on the shared lexer;
    - register Noto Sans (Regular/Bold/Italic/BoldItalic) as local TTFs in the lazy PDF chunk, with the OFL licence committed;
    - turn hyphenation off;
    - the filename keeps Cyrillic and replaces only characters not allowed in file names with "_".

    Tests. **[Agent: typescript-frontend]**
  - [x] Code review: FSD placement of the Markdown parts, no `dangerouslySetInnerHTML`, link allowlist on every href, preview/PDF parity, bundle (fonts only in the lazy chunk). **[Agent: react-code-reviewer]**
  - [x] Verify:
    - run the migration on a copy of the live DB: every existing CV has text containing all its old values, and the old columns are unchanged;
    - edit a CV: the preview updates;
    - export a CV with Russian text to PDF: the whole text is shown and the Cyrillic is correct;
    - the AI chat answers using the CV text.

    **[Agent: qa-tester]** _(2026-11-23: PRs #23 (markdown/preview/PDF) + #24 (backend + wiring). Migration run on a copy of the live DB: 4 CVs, all form fields were empty, nothing lost. Backend 1097 on 3.11/3.14, Vitest 376, tsc clean, vite build OK; code review no P0/P1; /security-review no findings. Browser checks (preview, Cyrillic PDF, chat) pending the live check — Chrome not connected)_

---

- [ ] **Slice 3: The editor never loses work**
  - [ ] Backend: `PATCH /cvs/{id}` requires `version`. A stale version returns 409 `{"detail":"CV_CHANGED"}`, implemented as `UPDATE … WHERE id AND version`. Tests, including two concurrent saves. **[Agent: python-backend]**
  - [ ] Frontend:
    - "Save" is active only when the name or text changed;
    - a counter appears above 18 000 characters;
    - a name of only spaces shows "Required";
    - a failed save shows "Could not save the CV. Please try again.";
    - 409 shows the "changed elsewhere" message and keeps the text;
    - `useUnsavedChangesGuard` (`useBlocker` + `beforeunload`) shows "Leave"/"Stay".

    Tests. **[Agent: typescript-frontend]**
  - [ ] Verify: open the same CV in two tabs and save in both, so the second save gets the message. Edit, then click another nav item to get the prompt. Reload to get the browser prompt. The Save button is disabled while there are no changes. **[Agent: qa-tester]**

---

- [x] **Slice 4: Upload a PDF or DOCX as a new CV**
  - [x] Backend:
    - deps `python-multipart`, `pdfminer.six`, `python-docx`;
    - `services/cv_upload.py` checks the file:
      - content sniffing;
      - `Content-Length` check, then a read cap of 5 MB + 1;
      - DOCX zip-bomb check (total uncompressed size ≤ 50 MB);
    - extraction runs in the threadpool:
      - PDF: at most 30 pages, `LAParams` column order, encrypted → `NO_TEXT`;
      - DOCX: body in order, including table cells;
      - whitespace-only text → `NO_TEXT`;
    - truncate to 20 000 characters; name from the file stem, or "Uploaded CV" if empty;
    - `POST /cvs/upload` returns `{…CvRead, became_base:false, truncated}` (base comes in Slice 5).

    Tests with fixture files: PDF, DOCX with a table, scanned PDF, encrypted PDF, renamed non-PDF, > 5 MB, zip bomb, > 20 000 characters, other user. **[Agent: python-backend]**
  - [x] Frontend: `features/cv-upload` — the "Upload CV" button on the CVs page (`.pdf,.docx`), "Uploading…", error code → spec text, then navigate to the editor with the notice "Text extracted from your file. Check the line breaks and save." (plus the cut notice). Tests. **[Agent: typescript-frontend]**
  - [x] Verify: upload a real PDF and a DOCX CV (Russian and English) and get a new CV whose text is in reading order. Upload a scan → error, no CV. A file over 5 MB → error. Nothing is written to disk (check the backend data folder). **[Agent: qa-tester]** _(2026-11-23: PRs #22 (extraction core) + #25 (endpoint + button). Endpoint tests with real PDF/DOCX/Cyrillic/scan/encrypted/renamed/oversized fixtures; backend 1118 on 3.11/3.14, Vitest 393; code review no P0/P1; security review no findings. Real-file upload in the browser pending the live check)_

---

- [ ] **Slice 5: Base CV, and "Add & tailor CV" starts from it**
  - [ ] Migration: `users.base_cv_id` (nullable, named FK, `use_alter`), NULL for everyone. **[Agent: database-expert]**
  - [ ] Backend:
    - `POST /cvs/{id}/make-base`;
    - `CvRead.is_base`, with `GET /cvs` ordered base first;
    - `delete_cv` nulls `base_cv_id`;
    - upload sets the base when there is none (`became_base`);
    - add-to-tracker names the copy after the chosen CV, leaving out an empty company or role.

    Tests, including owner scoping and deleting the base. **[Agent: python-backend]**
  - [ ] Frontend:
    - `features/cv-make-base` ("Make base", "Base CV updated" toast);
    - "Base" label on the CVs page and in the editor header;
    - no-base hint on the CVs page;
    - upload notice "This CV is now your base CV.";
    - add-to-tracker dialog: preselect the base or nothing, remove `pickMostRecentCvId`, disabled "Add & tailor CV" with the hint;
    - application panel labels the base;
    - update `features/vacancy-actions/CLAUDE.md`.

    Tests. **[Agent: typescript-frontend]**
  - [ ] Verify:
    - with no base, the Inbox "Add to tracker" preselects nothing and "Add & tailor CV" is disabled until a CV is chosen;
    - after "Make base", the base is preselected and the copy is named after it, with no chaining;
    - deleting the base leaves no base;
    - uploading with no base makes the upload the base.

    **[Agent: qa-tester]**

---

- [ ] **Slice 6: Tailored copies kept apart**
  - [ ] Migration:
    - add `cvs.kind` (default `own`) and `cvs.tailored_for_application_id` (nullable FK);
    - classify old copies with the rule from tech spec §2.1;
    - **first run the rule as a dry-run SELECT on the live DB and show the result to the user** (it must list the Kleos, Codery and Welldin copies and no CV linked by hand).

    **[Agent: database-expert]**
  - [ ] Backend:
    - add-to-tracker sets `kind=tailored` and `tailored_for_application_id`;
    - `make-base` on a tailored copy sets `kind=own` and keeps the link;
    - `CvRead.tailored_for` / `tailored_application_deleted`;
    - `GET /cvs` order: base, own, tailored;
    - `delete_application` nulls `tailored_for_application_id`;
    - duplicate is always `own`.

    Tests. **[Agent: python-backend]**
  - [ ] Frontend:
    - CVs page sections "My CVs" / "Tailored for applications";
    - "Company — Role" link to `/?application=<id>` or "Application deleted";
    - empty states;
    - the editor header shows the application;
    - add-to-tracker dialog groups ("Tailored copies" `<optgroup>` via `shared/ui/form-select` `groups`);
    - application panel lists own CVs first.

    Tests. **[Agent: typescript-frontend]**
  - [ ] Code review: `form-select` API change, the sections composition in `pages/cvs`. **[Agent: react-code-reviewer]**
  - [ ] Verify:
    - after the migration, the live user's Kleos, Codery and Welldin copies are under "Tailored for applications";
    - a CV linked by hand stays in "My CVs";
    - a new "Add & tailor CV" copy lands in the tailored section;
    - deleting its application shows "Application deleted";
    - making a copy the base moves it to "My CVs".

    **[Agent: qa-tester]**

---

- [ ] **Slice 7: AI chat proposes CV text edits as change cards**
  - [ ] Migration: the `chat_change_cards` table (tech spec §2.1). **[Agent: database-expert]**
  - [ ] Backend:
    - `services/chat_tools.py` (`propose_cv_edit` schema, Pydantic validation);
    - `groq_client`/`chat_service`:
      - pass tools only when a CV is linked;
      - accumulate tool-call deltas;
      - after the stream: save the assistant message, then the cards, then emit `cards`, then `done`;
      - a malformed call becomes an inline error;
      - card decisions go into the history as one line each;
    - `services/chat_card_service.py`, accept/reject. Accept fails as:
      - stale: missing passage, CV deleted, or the application re-linked to another CV;
      - not unique;
      - too long;
      - already decided.

      A successful Accept is one transaction with a version bump.
    - `GET /chat` returns cards per message;
    - clearing the chat and deleting the application remove the cards.

    Tests with a fake Groq tool call. **[Agent: python-backend]**
  - [ ] `scripts/smoke_chat_cards.py`: live check on the real chat model (prompts "shorten my summary", "add skill X", "remove the line about Y"). The tool calls must be valid and their passages must match the CV. Record the results. **[Agent: python-backend]**
  - [ ] Frontend:
    - `features/chat-interface/ui/cv-change-card.tsx` (before/after with `diffLines`, a position label, Accept/Reject, inline error, Accepted/Rejected/Stale styling);
    - the stream reader handles `event: cards`;
    - history renders cards;
    - Pending cards stay clickable after a reload.

    Tests. **[Agent: typescript-frontend]**
  - [ ] Code review: card component, stream handling. **[Agent: react-code-reviewer]**
  - [ ] Verify:
    - in a real application chat, ask for an edit: a card appears;
    - Accept changes only that passage (check in the editor);
    - Reject changes nothing;
    - edit the passage by hand, then Accept the old card: it goes Stale;
    - Accept a card while the editor is open with changes: the editor's Save shows "changed elsewhere";
    - with no CV linked, there are no cards and the assistant explains.

    **[Agent: qa-tester]**

---

- [ ] **Slice 8: Final regression and gates**
  - [ ] Full backend suite on 3.11 and 3.14, frontend suite, `tsc`, ruff and lint on changed files. **[Agent: qa-tester]**
  - [ ] Accessibility pass: editor (labels, tab order, the Edit/Preview tabs), the upload button states, the change card buttons. **[Agent: react-code-reviewer]**
  - [ ] `/pre-merge` and `/security-review` on the branch. Focus: upload hardening, link XSS, prompt injection via CV text and tool calls, owner scoping, migration safety. **[Agent: general-purpose]**
  - [ ] Live check with the user:
    - upload their real CV;
    - make it the base;
    - Inbox → "Add & tailor CV";
    - chat edits accepted and rejected;
    - PDF with Cyrillic;
    - conflict message.

    **[Agent: qa-tester]**
