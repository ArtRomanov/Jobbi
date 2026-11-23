# Tasks: Web Page and Aggregator Sources

Conventions for every slice:
- Tests ship inside the slice that adds the behavior (pytest with respx and a file-backed SQLite where concurrency matters; Vitest + MSW with a handler for every new endpoint).
- Frontend tools run from `frontend/node_modules/.bin` (as in spec 009). Regenerate `schema.d.ts` with `pnpm generate:types` (backend on :8003) after any API change.
- Backend runs on Python 3.11 (Docker) and 3.14 (local venv); run the suite on both before a slice is marked done.
- Library APIs (httpx `sni_hostname` extension, trafilatura `extract`, lxml parser options, BeautifulSoup) are checked against current docs via context7, not memory.
- Every new HTML/RSS fixture is a saved copy of a real page from the 2026-11-23 probe (geekjob, ingamejob, hirify, careerspace, ostrovok, yandex, hirehi, a Wrike-like page with Greenhouse links, ApprovalMax RSS).
- Each schema change gets its own Alembic migration inside the slice that needs it.

---

- [x] **Slice 1: Teamtailor company boards**
  - [x] Parsing: `<sub>.teamtailor.com` → kind `teamtailor` (anchored; requests only to `https://<sub>.teamtailor.com/jobs.rss`); board-error rule switched to the parsed host suffix (`greenhouse.io`, `lever.co`, `teamtailor.com`) so `clever.com` is not a board; error text mentions Teamtailor. `VACANCY_SOURCE_KINDS` and `SourceKind` gain `teamtailor` (fits `String(16)`, no migration). Hostile-input tests (`teamtailor.com.evil.com`, look-alikes). **[Agent: python-backend]**
  - [x] `fetchers/teamtailor.py`: RSS via lxml (`resolve_entities=False`, `no_network=True`, `huge_tree=False`), channel title → display name, items → `RawPost` (`tt:<sub>/<numeric id>`, `pubDate`, description → text via `html_to_text`). Wire into `board_scan` (`BOARD_KINDS`, `fetch_board`, `board_key_prefix`) and the live check on add. Dependency `trafilatura>=1.8` (brings lxml; Apache-2.0 from 1.8). Fixture tests incl. an entity-bomb XML. **[Agent: python-backend]**
  - [x] Frontend: `SOURCE_KIND_LABELS.teamtailor`, add-form label "Add a channel, job board or page". Tests. **[Agent: typescript-frontend]**
  - [x] Verify: curl add `approvalmax.teamtailor.com` → 201 with the company name; `clever.com/careers` is not rejected as a board link (still 400 until Slice 2, with the generic message); worker first scan stores jobs from the last 7 days, next `check_all` evaluates nothing old. **[Agent: qa-tester]** _(2026-11-23 on :8013: 9/9 checks passed — ApprovalMax 201, duplicates 409, unknown board 400, look-alikes rejected, clever.com gets the non-board text; first scan 6 seen keys / 0 pending (newest job Nov 6, older than 7 days); check_all adds nothing)_

---

- [x] **Slice 2: Add a web page source with preview (watching starts, no cards yet)**
  - [x] Migration: `vacancy_sources.url` (2048), `url_hash` (64) with UNIQUE (`user_id`, `url_hash`), `job_link_contains` (100). Kind `web`; web `handle` = source id. **[Agent: database-expert]**
  - [x] `fetchers/safe_http.py`: http/https, ports 80/443, resolve + reject non-global addresses (unwrap IPv4-mapped, block NAT64 explicitly), pinned IP with `Host` + `sni_hostname`, dedicated client `trust_env=False`, manual redirects ≤ 5 re-checked per hop, 15 s total via `asyncio.timeout`, 5 MB capped read (generalized from `board_http`), HTML content types only. Tests: private/loopback/link-local/NAT64/mapped, redirect to private, rebinding resolver, proxy env ignored, size and type limits. **[Agent: python-backend]**
  - [x] `fetchers/web_listing.py` (BeautifulSoup): job links with/without `job_link_contains`, same host or subdomains, titles, next page (`rel=next`, `page`/`p` + 1), using `normalize_url`. Fixture tests for every probed site incl. hirehi → zero jobs. **[Agent: python-backend]**
  - [x] Parsing: any other http(s) link → `web`; `MAX_INPUT_LENGTH` 2048 for links; non-http → "This link can't be used". `POST /vacancy-sources/preview` (`{input, job_link_contains?, source_id?}`; non-web → `{kind}` with no network; web → page 1, `found_count`, 5 titles). `POST /vacancy-sources` for web: listing up to 5 pages, then one transaction inserts the source (`initial_scan_completed_at = now`, default name = domain or user name ≤ 100) and a seen key per listed vacancy (`web:<source_id>/<sha256>`). Duplicate by `url_hash` → 409; 30-source limit; all error texts from functional spec 2.1. Source schema: `url`, `job_link_contains`, `watching_since`. API tests incl. "preview never writes". **[Agent: python-backend]**
  - [x] Frontend: `previewVacancySource`, extended `addVacancySource`; Add calls preview, non-web kinds create directly; inline `SourcePreview` (found N, 5 titles in site order, "Job link contains" + Re-check, optional name, Save/Cancel), hint "Sort the page by newest first before copying the link", `SOURCE_KIND_LABELS.web`, "Watching since <time>" in the row; zod for pattern and name. MSW + tests. **[Agent: typescript-frontend]**
  - [x] Code review: preview/add flow, FSD placement inside `features/manage-sources`, error handling. **[Agent: react-code-reviewer]** _(no P0/P1; P2/P3 fixed: focus after failed Save, types/validator moved to model, dead type, missing tests)_
  - [x] Verify: curl preview geekjob search, ingamejob listing, ostrovok with `/vacancy/` → counts and titles; hirehi → "No vacancies found…"; `http://localhost:8003/`, `http://192.168.1.1/`, `file:///etc/passwd` → "This link can't be used"; save geekjob → 201, seen keys = listed vacancies, duplicate → 409. Browser: preview, re-check with pattern, save, row shows "Watching since". **[Agent: qa-tester]** _(2026-11-23 on :8013: API 9/9 passed — geekjob 20 found, ingamejob 30, ostrovok 4, hirehi rejected, 7 internal/unsafe URLs refused in 2–15 ms without reaching the target, save geekjob → 100 seen keys over 5 pages in 7 s, 3 duplicate forms → 409; browser part not run — Chrome extension not connected; UI covered by component tests)_

---

- [ ] **Slice 3: Worker reads web pages and fills the Inbox**
  - [x] Migration: `vacancies.needs_detail` (bool, default false), `detail_attempts` (int, default 0). **[Agent: database-expert]**
  - [x] `fetchers/web_job.py`: JSON-LD `JobPosting` (text, `datePosted`, title, company) else `trafilatura.extract` on fetched HTML (never `fetch_url`); `cap_text`, `fits_columns`. Fixture tests (geekjob/yandex with JobPosting, ingamejob/ostrovok without). **[Agent: python-backend]**
  - [x] `web_scan.py` + `service.py`: `SUPPORTED_KINDS` gains `web`; `_SourceRef` carries `url`/pattern; listing pass up to 5 pages, stop at a page with a seen key and at the first failed page; new items → `pending` + `needs_detail`; `no_vacancies` / unreachable / refused-host read errors with spec texts and 24 h Unavailable. Detail step: also after a failed listing, only for users with a description, ≤ 30 rows oldest first, 1 s apart, exclude-word check on the filled text, 404/410 drops the row, 3 failures → title-only, budget 3 consecutive failures / 5 min per source, 40-min cap on the web part of `check_all`, listing steps of all sources first. Pending queries (`_users_with_pending`, `_next_batch`) skip `needs_detail`; title/company `coalesce` flipped for web in `_apply_evaluation` and `_promote_earlier_pending`; `waiting_count` excludes `needs_detail`. Worker tests from tech spec §4 incl. the no-network-in-transaction guard. **[Agent: python-backend]**
  - [ ] Verify: live — with a description set, a geekjob search and an ingamejob listing; force a seen key to be dropped (or wait for a new posting) and run `check_all`: cards appear with full text, AI title/company, date from JobPosting on geekjob; an exclude word that appears only in a job's body drops it; a 404 job is not evaluated; logs show per-source duration. **[Agent: qa-tester]**

---

- [ ] **Slice 4: ATS hint in the preview**
  - [x] `web_listing` collects Greenhouse/Lever/Teamtailor board links (incl. Greenhouse `embed/job_board?for=<token>`) and returns the most frequent as `ats_hint {kind, input, label}`; preview returns it. Fixture tests (Wrike-like page, embed link). **[Agent: python-backend]**
  - [x] Frontend: hint text "This page uses <Service> — add the board instead for full job texts and dates" + "Add the board" (adds like a pasted board link, closes the preview); the page itself can still be saved. Tests. **[Agent: typescript-frontend]**
  - [ ] Verify: preview `https://www.wrike.com/jobs/` → Greenhouse hint; "Add the board" adds the Greenhouse source with its name. **[Agent: qa-tester]**

---

- [ ] **Slice 5: Rename any source**
  - [ ] Migration: `vacancy_sources.default_name` (255, NOT NULL, backfilled from `display_name`). **[Agent: database-expert]**
  - [ ] `PATCH /vacancy-sources/{id}` with `{name}` only: ≤ 100 (400), empty → `default_name`; `name_is_custom` in the schema. Label fix: delete updates `vacancy_card_sources.label` to the current name before detaching (so "(removed)" shows the latest name). Tests incl. rename-then-delete. **[Agent: python-backend]**
  - [ ] Frontend: `updateVacancySource`; Edit button on every row opening `EditSourceDialog` (`Modal`, name field only for now); local state replaced after save; `onSourceEdited` → page bumps `refreshKey` so cards show the new name at once. Tests. **[Agent: typescript-frontend]**
  - [ ] Verify: browser — rename a Telegram channel and a web page; cards and the source filter show the new name without reload; clear the name → default returns; delete it → "(removed)" uses the latest name. **[Agent: qa-tester]**

---

- [ ] **Slice 6: Edit links and patterns (web edit, replace for other kinds)**
  - [ ] Migration: `vacancy_sources.initial_attempt_started_at`, `revision` (int, default 0). **[Agent: database-expert]**
  - [ ] Worker: initial-scan runner sets/clears `initial_attempt_started_at`; `_store_posts` source UPDATE gains `AND revision = :rev` (rowcount 0 aborts); detail step stops on a revision change. Tests incl. edit-during-fetch. **[Agent: python-backend]**
  - [ ] API: `PATCH` with `input` / `job_link_contains`. Edited source excluded from duplicate and 30-source checks (also in preview via `source_id`). Web: re-fetch up to 5 pages, one transaction updates url/hash/pattern, `revision += 1`, seen keys for what is listed, deletes the source's pending rows. Other kinds or a kind change: replace in one transaction via a no-commit helper split out of `delete_source` (with the label fix), new source gets the normal first scan. `409` "This source is being scanned — try again in a moment" while the lease is fresh (stale after 10 min). `editable` in the schema. Tests from tech spec §4 (edit at 30 sources, React→Vue pending deleted, Telegram replace, 409). **[Agent: python-backend]**
  - [ ] Frontend: `EditSourceDialog` gains link (all kinds) and pattern (web) with `SourcePreview` before Save; non-dismissable while saving; replace → `refreshRemovedSources`; Edit disabled when `!editable`; `mergePolledSources` copies `editable` and `watching_since`. Tests. **[Agent: typescript-frontend]**
  - [ ] Code review: Edit dialog, polling merge, FSD. **[Agent: react-code-reviewer]**
  - [ ] Verify: browser — geekjob `q=react` → `q=vue`: preview shows Vue, React cards stay, no React card arrives afterwards; Telegram channel → another channel: old cards under "<old name> (removed)", new one "Scanning…" with 7-day results; Edit disabled during a scan attempt and re-enabled without reload. **[Agent: qa-tester]**

---

- [ ] **Slice 7: Gates and live check**
  - [ ] `/pre-merge` gate on the branch (claims audit across API, worker and UI; hostile input incl. SSRF payloads; fault injection: slow site, 403, redirect loop, huge page). **[Agent: general-purpose]**
  - [ ] `/security-review` of the branch (SSRF guard, XML parsing, scraped text rendering). Fix findings. **[Agent: general-purpose]**
  - [ ] Update `features/manage-sources/CLAUDE.md`, `.env.example` unchanged check, README section on web sources (what works, JS sites unsupported, sort by newest). **[Agent: general-purpose]**
  - [ ] Live check from functional spec 2.5: ostrovok with/without pattern, geekjob search end-to-end within 2 hours of a real posting, edit filter, edit Telegram channel, localhost refused, Teamtailor board. Mark spec Status. **[Agent: qa-tester]**
