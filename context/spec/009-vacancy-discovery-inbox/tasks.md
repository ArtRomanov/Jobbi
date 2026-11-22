# Tasks: Vacancy Discovery (Inbox)

Conventions for every slice:
- Tests ship inside the slice that adds the behavior (pytest with respx and a file-backed SQLite where concurrency matters; Vitest + MSW with a handler for every new endpoint).
- Frontend tools run from `frontend/node_modules/.bin` (pnpm is broken on this machine; never npm). Regenerate `schema.d.ts` with the backend on :8003 after any API change.
- Backend runs on Python 3.11 (Docker) and 3.14 (local venv); run the suite on both before a slice is marked done.
- Library APIs (BeautifulSoup, APScheduler 3.x, respx, Groq JSON mode) are checked against current docs via context7, not memory.

---

- [x] **Slice 1: Inbox page with Telegram channel sources**
  - [x] Pre-checks, recorded in technical-considerations.md (Groq limits already recorded 2026-11-22): whether `boards-api.greenhouse.io` serves an EU board token; response size of a large Lever board (`mode=json`). **[Agent: general-purpose]**
  - [x] Models + one Alembic migration for `vacancy_sources` and `vacancy_search_settings` (later tables get their own migrations). **[Agent: database-expert]**
  - [x] Source input parsing (Telegram forms only for now; anchored patterns, hostile-input tests), live channel check via `t.me/s/<name>` (10 s, fixed host), `GET/POST/DELETE /api/v1/vacancy-sources` with 400/409 messages, 30-source limit, per-user isolation; router included. Tests. **[Agent: python-backend]**
  - [x] Extend `shared/api/handle-api-error.ts` (string `detail` first) + `getErrorMessage`. Add `shared/ui` `EmptyState`. Create `entities/vacancy-source/`, `features/manage-sources/` (add input with inline error, list with remove), `pages/inbox/` with route `/inbox` and an "Inbox" nav item (no badge yet). MSW handlers + tests. **[Agent: typescript-frontend]**
  - [x] Code review: FSD placement, error helper, page composition. **[Agent: react-code-reviewer]**
  - [x] Verify: curl add `@durov` (public) → 201; add a nonexistent channel → 400 with the exact text; duplicate → 409; another user's id → 404. In the browser: Inbox page shows empty state, add/remove a channel, inline errors appear. **[Agent: qa-tester]** _(2026-11-22: API checks 9/9 passed; browser part not run — Chrome extension not connected; UI covered by component tests, re-check in Slice 9 live test)_

---

- [x] **Slice 2: Search description and exclude words**
  - [x] `PATCH /api/v1/vacancy-search-settings` (partial; description ≤ 500, ≤ 50 exclude terms 1–64 chars, normalized), settings + `status` in `GET /vacancy-sources`. Tests. **[Agent: python-backend]**
  - [x] `shared/ui` `ChipInput`. Sources panel: description textarea (`maxLength` 500, paste cut, counter), exclude-word chips with the 50 limit message, "Describe what you're looking for…" hint when empty. Tests. **[Agent: typescript-frontend]**
  - [x] Verify: browser — save description, reload, it persists; 501st char blocked; 51st word shows the message; hint disappears after saving a description. **[Agent: qa-tester]** _(2026-11-22: API verified with curl — normalization, limits, error texts; browser part pending the Chrome extension, UI covered by 26 component tests)_

---

- [x] **Slice 3: Discovery worker finds Telegram vacancies (read-only Inbox)**
  - [x] Migration: `vacancy_seen_keys`, `vacancies`, `vacancy_card_sources`. **[Agent: database-expert]**
  - [x] Settings `GROQ_DISCOVERY_MODEL` (default `qwen/qwen3.8-27b`), `DISCOVERY_DAILY_EVAL_LIMIT` in `config.py` and `.env.example`; change the `GROQ_MODEL` default to `qwen/qwen3.8-27b` in both; treat `model_not_found` as a transport error; deps `beautifulsoup4`, `apscheduler>=3.10,<4`, dev `respx`. **[Agent: python-backend]**
  - [x] `app/discovery/`: `__main__.py` (httpx WARNING, scheduler: hourly `check_all`, every-minute `run_initial_scans`, shared lock, `max_instances=1`), `fetchers/telegram.py` (paging until known key / 7-day cutoff, job-link extraction; HTML fixture tests), `prefilter.py`, `evaluator.py` (Groq JSON mode `{"results": [...]}`, batches of 5 paced 30 s apart, 1 500-char post text, stop on 429, match rule and fit levels from functional spec 2.2, fenced post text, Pydantic validation), `initial_scan.py`, `service.py` (no network I/O inside transactions). Unit + worker tests incl. reference cases as fixtures and a hostile post. **[Agent: python-backend]**
  - [x] `GET /api/v1/vacancies` (filters by label, state, sort with CASE fit order, pagination) and `GET /vacancies/new-count`. Tests. **[Agent: python-backend]**
  - [x] `discovery` service in `docker-compose.yml` (same image, `backend-data` volume, env, `depends_on: backend`); document `alembic upgrade head` before start. **[Agent: devops-infra]**
  - [x] `shared/ui` `Badge`. `entities/vacancy/` (types, list/new-count API, `VacancyCard` with 300-char preview + Show more, `useNewVacancyCount` + `notifyVacanciesChanged`). Inbox list on the page; nav badge in `app/layout.tsx`; Sources panel shows "Scanning…" and last-checked, polls every 5 s while scanning and refreshes the list when a scan ends. Tests. **[Agent: typescript-frontend]**
  - [x] Live smoke of the evaluator prompt on the functional-spec reference cases with the real Groq model; record results; adjust the prompt until all pass. **[Agent: python-backend]**
  - [x] Verify: start the worker; add a busy public job channel and a description; within a few minutes the Inbox shows rated cards with reasons, badge counts them, "Scanning…" ends without reload; a post with an exclude word is not shown; rerun `check_all` → nothing evaluated twice (check Groq call count in logs). **[Agent: qa-tester]** _(2026-11-22 live run on @forfrontend: 13 posts, 12 evaluated, 1 excluded, 5 matches shown with reasons, no format errors after per-item validation; new-count 5; browser part pending the Chrome extension)_

---

- [ ] **Slice 4: Inbox actions — open, dismiss with undo, filters and sort**
  - [ ] `POST /vacancies/{id}/seen`, `/dismiss`, `/restore`; `removed_labels` in `GET /vacancy-sources`; source delete clears references (no FK cascade on SQLite). Tests. **[Agent: python-backend]**
  - [ ] Toast gains an optional action/link. `shared/ui` `SegmentedControl` (replace dashboard's private `TabButton`). `features/vacancy-actions/` (Open source → seen + new tab; Dismiss + 5 s Undo, ends on leaving the page). `features/inbox-filters/` (source by label incl. "(removed)", new/seen, sort). Badge refresh after every action. Tests. **[Agent: typescript-frontend]**
  - [ ] Code review: toast API change, SegmentedControl replacement in dashboard, FSD. **[Agent: react-code-reviewer]**
  - [ ] Verify: browser — Open source opens the post and the badge drops; Dismiss → Undo restores as seen; Dismiss without Undo → gone after reload; filters combine; fit sort is High→Medium→Low; remove a source → its cards filter under "(removed)". **[Agent: qa-tester]**

---

- [ ] **Slice 5: Add to tracker and "Add & tailor CV"**
  - [ ] Extract `application_service.build_application` and `cv_service.build_cv_copy` (no commit); existing functions wrap them; `delete_application` clears `vacancies.application_id`. Existing tests stay green. **[Agent: python-backend]**
  - [ ] `POST /vacancies/{id}/add-to-tracker` (conditional UPDATE race guard, normalized duplicate check with `allow_duplicate`, optional `base_cv_id` copy named and cut to 255, one commit); `existing_application` in the list response. Tests incl. concurrent double add and rollback when the CV copy fails. **[Agent: python-backend]**
  - [ ] `shared/ui` `Modal` (focus trap, Escape, focus return). `AddToTrackerDialog` (zod: company/role required; notes; base CV select defaulting to most recently updated; duplicate warning with Open it / Add anyway; Add & tailor CV disabled without CVs). Chat page pre-fills an unsent `draft` from router state and clears it. Dashboard opens `?application=<id>`. Success toast with link. Tests. **[Agent: typescript-frontend]**
  - [ ] Code review: Modal accessibility, chat draft, dashboard deep link. **[Agent: react-code-reviewer]**
  - [ ] Verify: browser — Add to tracker → application in Researching with notes and link, toast link opens it; Add & tailor CV → CV copy linked, chat opens with the unsent draft, reload does not re-fill; existing link → warning; double click → one application. **[Agent: qa-tester]**

---

- [ ] **Slice 6: Greenhouse and Lever company sources**
  - [ ] Parsing for Greenhouse (EU links → same token, standard API host), Lever US/EU (`lever`/`lever_eu`), look-alike host tests; live validation; Greenhouse name from the board, Lever name from the slug. **[Agent: python-backend]**
  - [ ] `fetchers/greenhouse.py` (list without content, content only for unseen jobs), `fetchers/lever.py` (region host, pages of 50 via skip/limit, 5 MB cap per request); board initial scan records all listed jobs as seen, evaluates only the last 7 days, none alerted. JSON fixture tests. **[Agent: python-backend]**
  - [ ] Verify: add a real Greenhouse board and a real Lever board (US and EU if found); recent matching jobs appear with company and role; next `check_all` evaluates nothing old. **[Agent: qa-tester]**

---

- [ ] **Slice 7: Telegram alerts and daily summary line**
  - [ ] Move the RetryAfter send logic into `app/core/telegram_send.py` taking a `Bot`; bot uses it unchanged in behavior (existing bot tests green). **[Agent: python-backend]**
  - [ ] `alerts.py`: one message per user per `check_all` run for cards that became new in this run (not from initial scans); exact text from functional spec 2.4; `alert_handled_at` set in every case. `summary_service`: "📥 N new vacancies in Inbox" incl. the zero-applications branch. Tests. **[Agent: python-backend]**
  - [ ] Verify: live — with Telegram linked, a new matching post in a watched channel produces one grouped bot message after the next check; adding a source produces no message; `/summary` shows the Inbox line; unlink + new matches + relink → no message about old cards. **[Agent: qa-tester]**

---

- [ ] **Slice 8: Resilience — limits, outages, unavailable sources, retention, reposts**
  - [ ] Daily cap per user local day with `limit_reached_on` and `waiting_count`; AI transport failures → `ai_failing_since`; poison post split + 3 attempts; source `failing_since` → Unavailable after 24 h with the three reasons; first-scan backoff; daily `cleanup` (30-day cards, 7-day pending only without description); repost merge by `job_link` into new/seen/dismissed via `vacancy_card_sources`. Tests with fixed clock. **[Agent: python-backend]**
  - [ ] Sources panel notices: daily limit with N waiting, AI unavailable, Unavailable source with reason; card shows all merged sources. Tests. **[Agent: typescript-frontend]**
  - [ ] Verify: simulate Groq down (bad key) → posts stay pending, notice after 1 h (shortened clock in a test run), recover → evaluated; set limit to 3 → notice and next-day processing; add a channel then make it unreachable (fake handle via test DB) → Unavailable; repost of the same job link in two channels → one card with two sources. **[Agent: qa-tester]**

---

- [ ] **Slice 9: Final regression and gates**
  - [ ] Full backend suite on 3.11 and 3.14, frontend suite, `tsc`, lint on changed files. **[Agent: qa-tester]**
  - [ ] Accessibility pass on the Inbox page, Modal and ChipInput (keyboard only, screen-reader labels). **[Agent: react-code-reviewer]**
  - [ ] `/pre-merge` and `/security-review` on the branch (SSRF patterns, prompt injection, XSS, per-user isolation). **[Agent: general-purpose]**
  - [ ] Live check: real channel + Greenhouse board → Inbox fills with no bot burst → hourly alert → Add & tailor CV → Dismiss + Undo. **[Agent: qa-tester]**
