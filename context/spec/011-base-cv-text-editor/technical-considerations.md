<!--
This document describes HOW to build the feature at an architectural level.
It is NOT a copy-paste implementation guide.
-->

# Technical Specification: Base CV, File Upload and Text CV Editor

- **Functional Specification:** [functional-spec.md](functional-spec.md)
- **Status:** Draft
- **Author(s):** Poe (AI Technical Architect), with codebase analysis by the python-backend and typescript-frontend agents (2026-11-23)

---

## 1. High-Level Technical Approach

- **Data:** a CV becomes one text column. The old structured columns stay, unused, for one release as the rollback path. One Alembic migration adds the new columns, converts every CV to text, classifies old tailored copies and leaves every user with no base CV.
- **Base CV:** a nullable pointer `users.base_cv_id`. "At most one base" then holds by construction, on SQLite and PostgreSQL alike.
- **Concurrency:** an integer `cvs.version` is checked on every write (editor save and card Accept). A stale write gets 409.
- **Upload:** a new multipart endpoint sniffs the content, extracts text with pdfminer.six or python-docx in a worker thread under size and page caps, and creates an own CV. The file is never written to disk.
- **AI change cards:** these are built for the first time; spec 008 was never implemented. Scope is CV text only. The chat model gets one tool, `propose_cv_edit`. The streamed reply carries the text tokens and, at the end, the cards. Cards are persisted, and Accept and Reject are separate endpoints.
- **Frontend:**
  - the form editor is replaced by a text editor with a Markdown preview;
  - preview and PDF share one Markdown lexer (`marked`) walked into React and react-pdf elements;
  - the PDF bundles a Unicode font with Cyrillic (Noto Sans);
  - the app moves to a data router, so `useBlocker` can guard unsaved changes.

Affected: `backend/app/{models,schemas,services,api/v1}` (CV, chat, vacancy, application), Alembic, and on the frontend `entities/cv`, `features/{cv-editor→cv-text-editor, cv-pdf, cv-upload, cv-make-base, chat-interface, vacancy-actions, application-panel}`, `pages/{cvs, cv-editor, chat}`, `app/` (router), `shared/{ui,lib}` and the test utils.

---

## 2. Proposed Solution & Implementation Plan (The "How")

### 2.1 Data model

| Table | Column | Type | Notes |
|---|---|---|---|
| `cvs` | `content` | Text NOT NULL, default `''` | The whole CV text (≤ 20 000 characters, enforced by the API) |
| `cvs` | `kind` | String(10) NOT NULL, default `'own'` | `own` / `tailored`. Kept as its own column so a tailored copy still shows "Application deleted" once its application is gone |
| `cvs` | `tailored_for_application_id` | String(36) NULL, FK → `applications.id` | Set only by "Add & tailor CV". Nulled by hand in `delete_application`, because SQLite does not enforce FKs |
| `cvs` | `version` | Integer NOT NULL, default 1 | Optimistic-concurrency token, incremented on every content or name write. `updated_at` is not used because SQLite `CURRENT_TIMESTAMP` only has 1-second resolution |
| `users` | `base_cv_id` | String(36) NULL, FK → `cvs.id` (named, `use_alter`) | The user's base CV. Nulled by hand in `delete_cv` |
| `cvs` | `personal_info`, `summary`, `work_experience`, `education`, `skills`, `languages` | unchanged | Not read or written by app code after this spec. Dropped in a follow-up migration one release later |
| `chat_change_cards` (new) | `id`, `application_id` (FK), `message_id` (FK → `chat_messages`, the assistant message), `cv_id` (String(36), no FK: a deleted CV makes the card Stale), `op` (`replace` / `insert` / `remove`), `before_text` Text, `after_text` Text, `position` (`start` / `end` / `after_line`, insert only), `anchor_text` Text NULL (insert after a line), `state` (`pending` / `accepted` / `rejected` / `stale`), `created_at`, `decided_at` NULL | | Index on `application_id`. Rows are removed by hand when the chat is cleared or the application is deleted |

The `chat_change_cards` columns are written as a list in the table above because it is one new table. The model will be `backend/app/models/chat_change_card.py`.

**Migration** (one revision on top of `031b22b73174`, `render_as_batch` is already on):
1. Add the columns and the table.
2. Data conversion runs as Python over `op.get_bind()`, with a **frozen copy** of the converter inside the migration (it does not import app code). The layout is the one in functional spec 2.2.
3. Old tailored copies get `kind='tailored'` and `tailored_for_application_id` when **all** of these hold:
   - `vacancies.application_id = applications.id` (the application came from the Inbox);
   - `applications.cv_id = cvs.id`;
   - `abs(cvs.created_at − applications.created_at) ≤ 5 s` (the two are created in one transaction).

   CVs linked by hand existed before their application, so they fail the third check. A copy whose application was re-linked or deleted cannot be detected and stays `own`, which is an accepted limitation. Before the migration runs, a dry-run SELECT on the live DB must show the Kleos, Codery and Welldin copies.
4. `users.base_cv_id` stays NULL for everyone (functional spec 2.2).
5. Downgrade drops the new columns and the table. The old fields are untouched, so the form data comes back as it was.

### 2.2 API contracts

| Method & path | Change | Request → Response |
|---|---|---|
| `GET /api/v1/cvs` | changed | → `CvRead[]`, base first, then own CVs, then tailored copies, each group by `updated_at` desc |
| `GET /api/v1/cvs/{id}` | changed | → `CvRead` |
| `POST /api/v1/cvs` | changed | `{name, content?}` → `CvRead` (always `kind=own`) |
| `PATCH /api/v1/cvs/{id}` | changed | `{name?, content?, version}`. If `version` is not the current one → **409** `{"detail": "CV_CHANGED"}`. Content over 20 000 characters → 422. Success → `CvRead` with the new `version` |
| `POST /api/v1/cvs/upload` | new | multipart `file`. 201 `CvRead` plus `{became_base: bool, truncated: bool}`. Errors: 413 `FILE_TOO_LARGE`, 415 `UNSUPPORTED_FILE`, 422 `NO_TEXT`, 400 `UPLOAD_FAILED`. The frontend maps each code to the spec's text |
| `POST /api/v1/cvs/{id}/make-base` | new | → `CvRead`. Sets `users.base_cv_id`, and also sets `kind=own` on a tailored copy, keeping `tailored_for_application_id` |
| `POST /api/v1/cvs/{id}/duplicate` | changed | Copies `name` and `content`; the copy is always `kind=own` |
| `DELETE /api/v1/cvs/{id}` | changed | Also nulls `users.base_cv_id` when this CV is the base, and marks pending cards on it stale |
| `POST /api/v1/vacancies/{id}/add-to-tracker` | changed | `base_cv_id` copies `content` and sets `kind=tailored` and `tailored_for_application_id`. The name comes from the chosen CV (functional spec 2.6) |
| `GET /api/v1/applications/{id}/chat` | changed | Each assistant message carries `cards: ChangeCardRead[]` |
| `POST /api/v1/applications/{id}/chat` | changed | The SSE stream keeps `token` / `done` / `error`, and adds `event: cards` (data `ChangeCardRead[]`) sent just before `done` |
| `POST /api/v1/applications/{id}/chat/cards/{card_id}/accept` | new | → `ChangeCardRead`. Card not pending → 409 `CARD_DECIDED`. Passage missing or CV deleted → 409 `CARD_STALE` (the card becomes stale). Passage appears more than once → 409 `PASSAGE_NOT_UNIQUE`. Result too long → 422 `TOO_LONG`. On success the CV's `version` is bumped |
| `POST /api/v1/applications/{id}/chat/cards/{card_id}/reject` | new | → `ChangeCardRead` |

**Shapes:**
- `CvRead = {id, name, content, kind, is_base, version, tailored_for: {application_id, company_name, role_title} | null, tailored_application_deleted: bool, linked_applications_count, created_at, updated_at}`.
- `ChangeCardRead = {id, op, before_text, after_text, position, anchor_text, state, cv_id, created_at, decided_at}`.

Every CV and card query is scoped to the owner (the same rule as the spec 009 fixes). Another user's ids → 404.

### 2.3 Backend components

| File | Responsibility |
|---|---|
| `app/models/cv.py`, `app/models/user.py`, `app/models/chat_change_card.py` | New columns and table |
| `app/schemas/cv.py` | `CvCreate` / `CvUpdate` (with `version`) / `CvRead` as above. The structured-field schemas are removed |
| `app/services/cv_service.py` | Create, update (version check via `UPDATE … WHERE id=? AND version=?`; rowcount 0 → `CvVersionConflict`), `make_base`, delete (nulls `base_cv_id`, unlinks applications, makes cards stale), `build_cv_copy` (copies content, takes `kind` and `tailored_for`) |
| `app/services/cv_upload.py` (new) | Sniffing:<br>• `%PDF-` → PDF;<br>• `PK\x03\x04` plus `[Content_Types].xml` and `word/document.xml` → DOCX.<br>Size check: `Content-Length`, then read at most 5 MB + 1.<br>DOCX zip-bomb check: sum of `ZipInfo.file_size` ≤ 50 MB.<br>Extraction runs in `run_in_threadpool`:<br>• PDF: pdfminer.six `extract_text` with `LAParams`, at most 30 pages; encrypted → `NO_TEXT`;<br>• DOCX: python-docx, walking the body in order including table cells.<br>Whitespace-only text → `NO_TEXT`. Truncate to 20 000 characters. Never write the file to disk |
| `app/api/v1/cvs.py` | The endpoints above |
| `app/services/chat_service.py`, `app/services/groq_client.py` | Feed the CV `content` to the system prompt inside `fence("CV", …)`. The prompt tells the model to quote passages exactly and to use only `propose_cv_edit` for edits. Pass `tools=[propose_cv_edit]` when a CV is linked. Stream text tokens, accumulate tool-call deltas and, after the stream ends, validate each call, store the cards and emit the `cards` event. The chat history sent to the model includes a one-line note per card decision ("Card accepted: …") |
| `app/services/chat_tools.py` (new) | The `propose_cv_edit` schema: `{op: replace\|insert\|remove, before?, after?, position?, anchor?}`. A Pydantic validator rejects malformed calls, which become an inline error message instead of a card |
| `app/services/chat_card_service.py` (new) | Accept: load the card (owner-scoped) and the CV; count occurrences of `before`/`anchor` in the **raw** CV text (0 → stale, more than 1 → not unique); build the new text; check its length; versioned update and card state change in one transaction. Reject: state only |
| `app/services/application_service.py` | `delete_application` nulls `cvs.tailored_for_application_id` and deletes the application's cards (next to the existing Vacancy nulling) |
| `app/services/vacancy_service.py` | Name the tailored copy after the chosen CV; pass `kind` and `tailored_for` |
| `pyproject.toml` | Add `python-multipart`, `pdfminer.six`, `python-docx` (pinned major versions, checked via context7 or PyPI at implementation time) |

### 2.4 Frontend components (FSD)

| Location | Responsibility |
|---|---|
| `app/index.tsx`, `app/router/` | Move from `<BrowserRouter>` / `<Routes>` to `createBrowserRouter` + `RouterProvider` with the same routes. `src/__tests__/utils.tsx` moves to `createMemoryRouter` |
| `entities/cv` | New `CvRead` fields; API `upload`, `makeBase`; `lib/cv-markdown.ts` (one `marked` lexer; the token walker handles heading 1–3, paragraph, strong, em, list, link and text, and shows any other token's `raw` as text); `ui/cv-text-preview.tsx` (React output, no `dangerouslySetInnerHTML`; links pass `isSafeCvLinkUrl`) |
| `shared/lib/is-safe-cv-link-url.ts` | http, https and mailto only. Every link in the preview and the PDF goes through it |
| `shared/ui/form-select.tsx` | Optional `groups` (`<optgroup>`) for the "Tailored copies" group |
| `features/cv-text-editor` (replaces `features/cv-editor`) | Name field, textarea (`maxLength` 20 000, paste cut), counter above 18 000, hint, preview with `useDeferredValue`, Edit/Preview `SegmentedControl` on phone width, dirty tracking, Save, 409 `CV_CHANGED` → the "changed elsewhere" message, `useUnsavedChangesGuard` (`useBlocker` plus `beforeunload`) |
| `features/cv-upload` | "Upload CV" button with a hidden file input (`.pdf,.docx`), the "Uploading…" state, error code → text, then navigate to the editor with the notice in router state |
| `features/cv-make-base` | The "Make base" action and the "Base CV updated" toast |
| `features/cv-pdf` | Rewrite `cv-document.tsx` on top of the shared lexer. `Font.register` loads Noto Sans (Regular, Bold, Italic, BoldItalic; Latin + Cyrillic) as local TTFs (Vite `?url`) inside the lazy PDF chunk only. The hyphenation callback is turned off. File name: characters not allowed in file names become "_" (Cyrillic is kept) |
| `features/chat-interface` | `ui/cv-change-card.tsx` (before/after, line diff via `diff`'s `diffLines`, position label, Accept/Reject, inline error, Stale styling); the stream reader handles `event: cards` |
| `features/vacancy-actions` | The dialog preselects `is_base`, or nothing. `pickMostRecentCvId` is removed. Grouped options and the hint |
| `features/application-panel` | The CV select lists own CVs first and labels the base |
| `pages/cvs` | The "My CVs" and "Tailored for applications" sections, the no-base hint, the "Company — Role" link to `/?application=<id>` or "Application deleted", and the Upload button |
| `pages/cv-editor` | Composes the text editor; shows the upload notice from router state |

New npm packages: `marked`, `diff`, and Noto font files committed under `frontend/src/shared/assets/fonts/` (OFL licence, licence file kept).

### 2.5 Logic notes

- **Markdown parity:** preview and PDF use the same lexer and token whitelist, so they cannot drift.
- **Card matching:** occurrences are counted in the stored raw text. The prompt copy is defanged (`<<<` → `<<`), so a passage containing `<<<` will fail to match and the card goes Stale. This is accepted.
- **Accept and the editor:** Accept bumps `version`, so an open editor's next Save gets 409 and the user's text stays put (functional spec 2.1).
- **Order:** the backend lands first (schema and API), then `schema.d.ts` is regenerated from `create_app().openapi()`, then the frontend.

---

## 3. Impact and Risk Analysis

- **System dependencies:**
  - Spec 009 add-to-tracker (copy naming, kind);
  - the application panel (CV select);
  - the AI chat (system prompt, streaming);
  - PDF export.

  The bot, metrics and the discovery worker do not read CVs.

| Risk | Mitigation |
|---|---|
| The migration misclassifies or loses data | Old columns are kept for one release; the dry-run SELECT runs on the live DB; the converter is unit-tested on every field; `alembic downgrade` is tested on a DB copy |
| Malicious uploads (zip bomb, PDF decompression bomb, slow parse) | 5 MB cap, compression-ratio check on DOCX, 30-page cap, threadpool. A per-parse timeout via a subprocess is a follow-up if slow parses show up |
| Starlette spools the whole request body before the size check | Check `Content-Length` first. Docker/nginx body limits are noted for deployment |
| Prompt injection through CV text or a pasted post | CV text inside `fence`; tool calls validated server-side; nothing is saved without Accept; cards are scoped to the application's own CV |
| Qwen tool-calling reliability on long CVs | Smoke script with fixed prompts ("shorten my summary", "add skill X"), run live before merge; malformed calls become inline errors |
| Prompt size (20k CV + notes + history) vs Groq limits | History is trimmed as today; the CV is sent once per turn; the risk is accepted at current volumes |
| Bundle size: fonts (~1–2 MB) and `marked`/`diff` | Fonts load only in the lazy PDF chunk; `marked` and `diff` are small (~60 KB together) |
| Link XSS (`javascript:`, `data:`) in the preview or PDF | `isSafeCvLinkUrl` on every href; HTML tokens shown as text; tests with hostile links |
| The router migration breaks pages or tests | Same route table, moved as is; full Vitest run; manual click-through of every route |
| SQLite does not enforce FKs | Nulling by hand in `delete_cv` and `delete_application`, with tests |

---

## 4. Testing Strategy

- **Backend (pytest, Python 3.11 and 3.14):**
  - the converter, on every field and on empty CVs;
  - the migration on a fixture DB: upgrade, the classification rule (Inbox copy vs linked by hand) and downgrade;
  - version conflict → 409;
  - make-base, including on a tailored copy;
  - delete nulls base, unlinks applications and makes cards stale;
  - upload: PDF, DOCX, scanned PDF, encrypted PDF, a renamed non-PDF, over 5 MB, a zip bomb, over 20k characters;
  - card Accept: replace, insert, remove, stale, not unique, too long, already decided;
  - streaming with a fake Groq tool call that emits the `cards` event;
  - owner scoping on every new endpoint.
- **Frontend (Vitest + MSW, a handler for every new endpoint):**
  - editor: dirty Save, counter, paste cut, 409 message, `useBlocker` prompt;
  - Markdown walker, with hostile links;
  - CVs page sections, base hint, upload states and errors;
  - add-to-tracker preselection and groups;
  - change card states and diff;
  - PDF filename;
  - full suite plus `tsc` after the router migration.
- **Live (with the user):**
  - upload a real PDF and DOCX CV (Russian and English);
  - mark the base, then "Add & tailor CV" from the Inbox;
  - in the chat, ask for edits and Accept/Reject;
  - edit in the editor while a card is accepted (conflict message);
  - export the PDF and check the Cyrillic.
- **AI smoke:** a script like `scripts/smoke_evaluator.py` for `propose_cv_edit` on the real chat model.
