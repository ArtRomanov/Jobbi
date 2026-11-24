<!--
This document describes HOW to build the feature at an architectural level.
It is NOT a copy-paste implementation guide.
-->

# Technical Specification: Web Page and Aggregator Sources

- **Functional Specification:** `context/spec/010-web-page-and-aggregator-sources/functional-spec.md`
- **Status:** Draft
- **Author(s):** Poe (AI Technical Architect)

---

## 1. High-Level Technical Approach

Two new source kinds plug into the spec 009 discovery pipeline (seen keys → exclude words → AI evaluation → Inbox → alerts), which stays unchanged:

- **`web`** — any http(s) listing page (aggregator search or career page). The API previews and saves it; the worker reads the listing hourly (up to 5 pages, stops at a page with a seen vacancy), creates `pending` cards with link + listing title, then a separate **detail step** opens up to 30 job pages per source per check and fills their text before the AI sees them.
- **`teamtailor`** — `<company>.teamtailor.com`, read from the public RSS feed `/jobs.rss` (title, link, `pubDate`, full HTML description per job); behaves like Greenhouse/Lever.

Plus **Edit** for every source (`PATCH`), a **preview** endpoint, and an **ATS hint** when a web page links to a Greenhouse/Lever/Teamtailor board.

Arbitrary URLs mean the worker and the API now fetch user-chosen hosts. All such requests go through one **guarded fetcher** (`safe_http`) that blocks private/loopback addresses, pins the resolved IP for the connection (no DNS rebinding), re-checks every redirect, and caps size and time.

**Systems affected:**
- Backend: 1 Alembic migration (columns on `vacancy_sources` and `vacancies`), parsing, source service (preview / create / update / replace), 5 new fetcher modules, a web scan + detail step in the worker, small evaluator/service adjustments.
- Frontend: `entities/vacancy-source` (2 API calls, regenerated types), `features/manage-sources` (inline preview, Edit modal, ATS hint, new labels).
- Dependencies: `trafilatura` (main-text extraction, brings `lxml`). No new env vars; no Docker changes.

**Verified 2026-11-23 by live requests** (curl, browser User-Agent; raw output in the session scratchpad):

| Site | Plain HTML has job links | Job link pattern | Paging seen in HTML | JobPosting JSON-LD on job page |
|---|---|---|---|---|
| geekjob.ru | yes | `/vacancy/<hex id>` | no | yes (`datePosted`) |
| ingamejob.com | yes | `/en/job/<slug>` | `?page=2…5` | no |
| hirify.me | yes | `/jobs/<id>-<slug>` | no | not checked |
| careerspace.app | partly (8 in HTML, rest via JS) | `/job/<id>` | no | no |
| hirehi.ru | **no** (cards have `data-id`, no `href`) | — | `?page=N` | — |
| career.ostrovok.ru | yes | `/vacancy/<id>` | no | no |
| yandex.ru/jobs | yes | `/jobs/vacancies/<slug>` | no | yes |
| avito, krisp, playrix | no (JS-rendered) | — | — | — |
| careers.manychat.com | 403 | — | — | — |

- ATS markers inside career pages: Wrike → 30 Greenhouse links, Tripledot → Greenhouse, Uzum → Huntflow, Salmon → Ashby, Align/BostonGene → Pinpoint, AIDigital → Recruitee.
- Teamtailor: `approvalmax.teamtailor.com/jobs.rss` → 200 `application/rss+xml`, channel `<title>` = company name, 6 items with `title`, `link` (`/jobs/<numeric id>-<slug>`), `pubDate`, `guid`, `description`.

**Invariant kept from spec 009:** no network I/O inside a database transaction (fetch → short write transaction → commit).

---

## 2. Proposed Solution & Implementation Plan

### 2.1 Data Model / Database Changes

One Alembic migration on top of the current head. Standard SQLAlchemy only.

**`vacancy_sources`** — new columns:

| Column | Type | Purpose |
|---|---|---|
| `url` | String(2048), NULL | Web only: normalized listing URL that is fetched |
| `url_hash` | String(64), NULL | Web only: sha256 of `url`; UNIQUE (`user_id`, `url_hash`) gives "Already in your sources" without a 2 KB index entry (NULLs for other kinds don't collide on SQLite or PostgreSQL) |
| `job_link_contains` | String(100), NULL | Web only: the optional pattern |
| `default_name` | String(255), NOT NULL | Name from the source itself (domain, board/channel title). Backfilled from `display_name`. `display_name` stays the effective name = user's name or `default_name`, so every downstream reader (`_live_labels`, filters) is untouched |
| `initial_attempt_started_at` | DateTime, NULL | Set by the worker when a first-scan attempt starts, cleared when it ends; Edit is refused while set (stale after 10 min = ignored, covers a crashed worker) |
| `revision` | Integer, NOT NULL, default 0 | Incremented by every Edit that changes what is fetched (edit-vs-fetch race). `_SourceRef` / `_load_sources` (`discovery/service.py`) carry `revision`, `url` and `job_link_contains`; the source UPDATE in `_store_posts` gains `AND revision = :rev`, and rowcount 0 aborts that store (same path as today's "source deleted mid-fetch"). The detail step re-reads the source's revision before each write and stops if it changed |

- `kind` gains `web` and `teamtailor` (fit `String(16)`); `VACANCY_SOURCE_KINDS` and the schema `SourceKind` Literal updated.
- **Web `handle` = the source's own id.** It is stable across edits, fits `String(64)`, and keeps `vacancy_card_sources.source_handle` and the `?source=` key valid after a link change.
  - Accepted trade-off: removing a web source and adding the same URL again creates a new id, so the filter shows "geekjob.ru (removed)" next to the live "geekjob.ru" (the 009 "re-added source becomes live again" rule, `vacancy_service.py:207-211`, does not apply to web). No old vacancy reappears: the re-added source records everything listed at save time as seen ("only new"). Edit is the way to change a web source without getting the "(removed)" entry.
- Teamtailor `handle` = company subdomain, lowercased.

**`vacancies`** — new columns:

| Column | Type | Purpose |
|---|---|---|
| `needs_detail` | Boolean, NOT NULL, default false | Web `pending` rows whose job page is not read yet; the evaluator skips them |
| `detail_attempts` | Integer, NOT NULL, default 0 | Failed job-page reads; at 3 the row is released to evaluation with its listing title as text |

**Seen keys** (`vacancy_seen_keys.external_key`, String(255)):
- Web: `web:<source_id>/<sha256(normalized job url)>` (105 chars). Per source, so repost merging by `job_link` across sources keeps working; history survives a link edit because the source id does not change.
- Teamtailor: `tt:<company>/<numeric job id from the link>`.

**Normalization:** reuse `discovery/normalize.py:normalize_url` (lowercase host, drop fragment, `utm_*` and trailing slash; other query parameters stay — they are the user's filters) for the listing URL, job URLs and dedupe; extend it only if default-port stripping is missing.

### 2.2 API Contracts

All under the existing router `app/api/v1/vacancies.py`, same auth, user scoping and error style (`400`/`409` with string `detail`).

| Method & Path | Request | Response | Notes |
|---|---|---|---|
| `POST /api/v1/vacancy-sources/preview` | `{input, job_link_contains?, source_id?}` | `200 {kind, default_name?, found_count?, titles?: string[≤5], ats_hint?: {kind, input, label} \| null}` | Never writes. Non-web kind → `{kind}` from parsing only, **no network call** (the client then calls create/PATCH, which does the live check once). Web: fetches page 1 only, 15 s total. `source_id` (edit context) excludes that source from the duplicate and 30-source checks. Errors: "This link can't be used", "Could not open this page", "No vacancies found on this page. Check the link or set 'Job link contains'.", "Already in your sources" (409), the 30-source limit |
| `POST /api/v1/vacancy-sources` | `{input, job_link_contains?, name?}` | `201 Source` | Existing endpoint, extended. Web: re-fetches the listing **up to 5 pages** (same paging as the hourly check), so "every vacancy listed at the moment of saving" is recorded; then one transaction inserts the source with `initial_scan_completed_at = now` and a seen key per listed vacancy. Page 1 with zero vacancies → the "No vacancies found" error. Teamtailor: live check like boards (RSS readable), then normal 7-day first scan by the worker |
| `PATCH /api/v1/vacancy-sources/{id}` | `{input?, job_link_contains?, name?}` | `200 Source` | The edited source is excluded from the duplicate and 30-source checks. Name only → update `display_name` (empty → `default_name`). Web link/pattern change → re-fetch (up to 5 pages), then one transaction: update `url`/`url_hash`/pattern, `revision += 1`, seen keys for what is listed now, and **delete the source's `pending` rows** (old-filter vacancies must not arrive after the edit). Telegram/board link change, or any kind change → **replace** in one transaction: a no-commit helper split out of `delete_source` (`vacancy_source_service.py:256-292`, which commits itself today) does the delete — including the label fix below — then the insert; the new source gets the normal first scan, and the new source gets its own default name unless the request sets a different name (an old custom name would make the replaced source's cards indistinguishable from the new one's). `409` "This source is being scanned — try again in a moment" while `initial_attempt_started_at` is fresh |

- **Source schema** gains: `url` (web), `job_link_contains`, `name_is_custom` (= `display_name != default_name`), `watching_since` (web: `initial_scan_completed_at`), `editable` (false while an attempt runs). The API enforces `name` ≤ 100 and `job_link_contains` 1–100 characters (400), not only the frontend.
- **Label fix (found in analysis):** before a source is deleted or replaced, set `vacancy_card_sources.label` to the source's current `display_name` for its rows, so "(removed)" shows the latest name, not the one at the time the card was found.
- **Input parsing** (`vacancy_source_parsing.py`): `MAX_INPUT_LENGTH` 200 → 2048 for http(s) links. Order: Telegram → Greenhouse/Lever → Teamtailor (`^(https?://)?<sub>.teamtailor.com(/…)?$`, requests only to `https://<sub>.teamtailor.com/jobs.rss`) → any other `http(s)` URL = `web`. The board error text gains Teamtailor and is shown only when the **parsed host** is or ends with `greenhouse.io`, `lever.co` or `teamtailor.com` — today's unanchored `_BOARD_DOMAIN_HINT` (`vacancy_source_parsing.py:77`) also matches `clever.com`, which must become a web source. Non-http schemes → "This link can't be used".

### 2.3 Guarded Fetcher (`backend/app/discovery/fetchers/safe_http.py`)

Used by the API (preview, save, edit) and the worker for every `web` request. Telegram, Greenhouse, Lever and Teamtailor keep their fixed-host clients.

| Rule | Detail |
|---|---|
| Scheme / port | `http`/`https` only; ports 80 and 443 only |
| Address check | Resolve the host (async `getaddrinfo`); reject if **any** address is not globally routable: unwrap `ipv4_mapped` IPv6 first, then `ipaddress` `is_global` false (loopback, private, link-local incl. `169.254.169.254`, CGNAT, multicast, reserved), and block NAT64 `64:ff9b::/96` explicitly (its `is_global` is True) → "This link can't be used" |
| IP pinning | Request the checked IP literal (IPv6 in brackets) with a `Host` header for the original name and `extensions={"sni_hostname": <name>}` (httpcore uses it for SNI and certificate verification), so no second DNS lookup happens |
| Client | A dedicated `httpx.AsyncClient(trust_env=False, follow_redirects=False)` — `trust_env=False` so `HTTP(S)_PROXY` variables cannot route around the check |
| Redirects | Followed manually, max 5; every hop repeats scheme, port and address checks; relative `Location` resolved against the current URL |
| Limits | 15 s **total** per request via `asyncio.timeout` (httpx timeouts are per phase); body read with the existing capped streaming read (`board_http.py:80-100` / `vacancy_source_check._fetch_capped`, generalized to text) at 5 MB decompressed; only `text/html` / `application/xhtml+xml` accepted for pages |
| Identity | `User-Agent: Mozilla/5.0 (compatible; Jobbi/1.0)` — honest name, browser-compatible prefix (some sites 403 unknown agents) |

### 2.4 Discovery Worker Changes (`backend/app/discovery/`)

| File | Responsibility |
|---|---|
| `fetchers/web_listing.py` (new) | Parse one listing page with BeautifulSoup (already a dependency) → `(jobs: [(url, title)], next_url, ats_hint)`. Candidate links: `<a href>` resolved to absolute, normalized, same host or its subdomains, no `mailto:`/`javascript:`/fragment-only. With `job_link_contains`: keep links whose URL contains it. Without: keep links whose path has a job-like segment (`job`, `jobs`, `vacanc`, `vakans`, `position`, `opening`, `career`, `role`) **followed by** another segment (slug or id), and that are not the listing URL itself. Dedupe, keep page order. Title = anchor text, else `title`/`aria-label`, ≤ 255. Next page: `<link rel=next>` / `<a rel=next>`, else an `<a>` to the same path with `page`/`p` = current + 1. ATS hint: links to Greenhouse/Lever/Teamtailor boards run through `parse_source_input`; the most frequent board wins. Greenhouse embed links (`/embed/job_board?for=<token>`) are rejected by `_GREENHOUSE_RESERVED` (`vacancy_source_parsing.py:66`), so the hint extracts `for=` from them explicitly |
| `fetchers/web_job.py` (new) | Read one job page → `(text, posted_at?, title?, company?)`. JSON-LD `JobPosting` first (`description` HTML → text via `board_http.html_to_text`, `datePosted`, `title`, `hiringOrganization.name`); else `trafilatura.extract` on the HTML already fetched by `safe_http` (**never** `trafilatura.fetch_url`, which would bypass the guard); text through `cap_text` (≤ 20 000), fields through `fits_columns` |
| `fetchers/teamtailor.py` (new) | RSS via `lxml` with `resolve_entities=False`, `no_network=True`, `huge_tree=False` (no XML bombs / external entities). Channel title → display name; item → `RawPost` (`posted_at` = `pubDate`, text from `description`) |
| `board_scan.py` | `teamtailor` added to `BOARD_KINDS`, `fetch_board` and `board_key_prefix` (`tt:`) |
| `web_scan.py` (new) | Hourly listing pass for one web source: fetch page 1…5 through `safe_http`, 1 s pause between pages; check keys with `_already_seen`; stop after the first page that contains a seen key. Returns new `(key, url, title)` items. Zero vacancies on page 1 → read error `no_vacancies` |
| `service.py` — listing | `SUPPORTED_KINDS` includes the new kinds. `_fetch_source` branches to `web_scan`; new items stored as `pending` + `needs_detail = true` (title = listing title, text empty); the exclude-word check at insert (`:629`) sees only the title here. `READ_ERROR_MESSAGES` gains `no_vacancies` → "No vacancies found — check the link or the 'Job link contains' field"; an unreachable page **and** a host that `safe_http` now refuses (DNS turned private) both map to "Could not reach the source". Initial-scan runner sets/clears `initial_attempt_started_at` |
| `service.py` — detail step | Runs per web source after the listing step, **also when the listing read failed** (rows already queued still progress), and only for users with a search description (rows of users without one wait; retention drops them after 7 days as in 009, so no pages are fetched for nothing). Up to 30 `needs_detail` rows, oldest first, 1 s apart. Success → text, `posted_at` (JobPosting date, else found time), then **`excluded(title, text)`**: a hit deletes the row and keeps the seen key, as at insert; otherwise `needs_detail = false`. 404/410 → the job is gone: delete the row, keep the seen key (no AI call). Other failure → `detail_attempts += 1`; at 3 → `needs_detail = false`, text = listing title. **Budget:** the step stops after 3 consecutive failures or 5 min per source; the rest waits for the next check |
| `service.py` — evaluation | The pending queries `_users_with_pending` (`:839`) and `_next_batch` (`:874-912`) exclude `needs_detail = true`. For `web` cards the AI's title/company win and the stored values (JobPosting or listing title) are the fallback — the `coalesce(stored, ai)` order is flipped for web in **both** places: `_apply_evaluation` (`:1105-1106`) and `_promote_earlier_pending` (`:803-804`) |
| `services/vacancy_service.py` | `waiting_count` (`:243`, drives "Daily limit reached — N posts are waiting") excludes `needs_detail` rows: they are not waiting for the AI yet |

Everything after evaluation (merge by `job_link`, alerts, retention, daily cap 150) is unchanged.

**Load and duration per web source per hourly check:** at most 5 listing pages + 30 job pages = 35 requests, 1 s apart. Each request can take up to 15 s, so without a cap one source could take ~9 min and 30 sources several hours — and `JobRunner` holds one lock for all jobs (`discovery/__main__.py:75-90`), which would also block `run_initial_scans` for new sources. Therefore: the listing step stops at the first failed page; the detail step has the budget above (3 consecutive failures or 5 min); and the whole web part of `check_all` stops at 40 min, leaving remaining detail work for the next check (listing steps of all sources run first, so new vacancies are queued everywhere before details). Each source's duration is logged.

### 2.5 Frontend (FSD)

| Slice | Change |
|---|---|
| `entities/vacancy-source/api/` | `previewVacancySource({input, job_link_contains?})`, `updateVacancySource(id, patch)`; `addVacancySource` gains optional `job_link_contains`, `name`; exported from `index.ts`. Types regenerated with `pnpm generate:types` (backend running; `schema.d.ts` is gitignored) |
| `features/manage-sources/ui/add-source-form.tsx` | Add calls preview first. Non-web kind → create immediately (today's flow). Web → inline `SourcePreview` under the form. Hint "Sort the page by newest first before copying the link". Label "Add a channel, job board or page" |
| `features/manage-sources/ui/source-preview.tsx` (new) | "Found N vacancies", up to 5 titles, "Job link contains" field + "Re-check", optional name (max 100), Save / Cancel, ATS hint with "Add the board". Shared by add and edit |
| `features/manage-sources/ui/edit-source-dialog.tsx` (new) | `Modal` (non-dismissable while a request runs): link, name, and for web the pattern; link/pattern change → `SourcePreview` before Save. On a replace, call `refreshRemovedSources` so the old name appears as "(removed)" |
| `features/manage-sources/ui/source-list-item.tsx` | "Edit" button (disabled when `!editable`), "Watching since <time>" for web |
| `features/manage-sources/lib/helpers.ts` | `mergePolledSources` (`:36-52`) also copies `editable` and `watching_since`, so Edit re-enables after an attempt without a reload |
| `features/manage-sources` ↔ `pages/inbox` | `SourcesPanel` gets an `onSourceEdited` callback; after any successful PATCH the page bumps `refreshKey` (`pages/inbox/ui/inbox-page.tsx:11-13`), so cards on screen show the new name at once (today only `onScanFinished` refreshes the list) |
| `features/manage-sources/lib/constants.ts` | `SOURCE_KIND_LABELS` for `web` ("Web page") and `teamtailor` (TypeScript forces them after regeneration) |
| `features/manage-sources/model/` | zod schema for pattern (1–100) and name (≤ 100); state for preview/edit in `use-manage-sources.ts`, replacing the item in local state after edit |
| `features/manage-sources/CLAUDE.md` | Updated with the new flows |

Edit and preview stay inside `features/manage-sources` (a separate feature slice could not import it). Inline styles with `colors` tokens, as today.

### 2.6 Dependencies

- `trafilatura>=1.8` (Apache-2.0 from 1.8.0; GPL before that), pulls `lxml`, also used for RSS. Only `trafilatura.extract` on already-fetched HTML is allowed; its own downloader is never used.
- No new env vars. Limits (5 pages, 30 details, 3 attempts, 15 s, 5 MB) are module constants.

### 2.7 Follow-up: Ashby, geekjob search, blocked sites (functional spec §2.6)

- **Ashby adapter** (`fetchers/ashby.py`): kind `ashby` (fits `String(16)`; no migration — `kind` has no DB check), handle = org slug lowercased. Parsing (`vacancy_source_parsing._ASHBY_LINK`): `(https?://)?jobs.ashbyhq.com/<org>[/<uuid>[/application]][/][?simple query]`, anchored fullmatch, `re.ASCII | IGNORECASE`, org `[a-z0-9]([a-z0-9._-]{0,62}[a-z0-9])?` (dots are real: `kraken.com`), `..` and reserved `embed`/`api` refused; host suffix list gains `.ashbyhq.com`. Only request: `GET https://api.ashbyhq.com/posting-api/job-board/<org>?includeCompensation=false` via `board_http.get_bytes` (no redirects, 15 s) with its own 32 MB cap — the answer repeats every description as plain text and HTML, measured 2026-11-23: openai 14.3 MB (14 268 354 bytes), notion 3.1 MB, manychat 0.37 MB; every other board keeps 5 MB — and the JSON parsed in a worker thread (`board_http.parse_json_body`: invalid JSON, bad bytes or too-deep nesting → `unreachable`, so add returns 400, not 500). Live shape (`manychat`, 21 jobs): `{jobs: [{id (uuid), title, location, jobUrl, publishedAt (ISO with offset), descriptionPlain, descriptionHtml, isListed, isRemote, ...}], apiVersion}`; unknown org → 404 → "Could not read this job board". The API has no organization name → display name = title-cased slug (as Lever). Jobs: string UUID-like `id`, http(s) `jobUrl` (stored, never fetched), `isListed: false` dropped, capped at 2 000, deduped. Key `ashby:<org>/<id>`; text `descriptionPlain` else `html_to_text(descriptionHtml)`, mapping in `asyncio.to_thread`; `posted_at` = `publishedAt` as naive UTC. Wired into `BOARD_KINDS` (7-day first scan), `fetch_board`, `board_key_prefix`, `vacancy_source_check.check_ashby_board`, `VACANCY_SOURCE_KINDS`, `SourceKind`. ATS hint: `_ATS_BOARDS.ashby` ("Ashby", `https://jobs.ashbyhq.com/{handle}`), plus the `jobs.ashbyhq.com/<org>/embed` script/iframe.
- **Site listing adapters** (`fetchers/site_listing.py`): `find_site_listing(url) -> SiteListing | None` (registry of matchers). `SiteListing.page_url(n)` builds the JSON URL of page n; `parse_page(data, n, job_link_contains) -> ListingPage` never raises. `web_scan.read_listing` uses it when it matches (JSON via `safe_http.fetch_json`, parse in a worker thread, next page built by the adapter on its fixed host) with the same 5-page limit, pause, time budget and stop-at-seen rule; every other link keeps the HTML path. Preview, add, edit and the worker all go through `read_listing`, so nothing else changes (keys `web:<source_id>/<sha256(url)>`, detail step via JSON-LD, exclude words, AI).
- **geekjob mapping** (from `/app/filters/vacancies/app.js`): host `geekjob.ru` / `www.geekjob.ru`, path `/vacancies` or `/vacancies/<n>`, no port/userinfo. Only the filters the site script reads from the page URL are copied: `qs` (trimmed, ≤ 200), `t` (≤ 50 comma-separated ids), `s` (+ the script's fixed `money=120000`), `pt`, `ih`, `rm`, `rl`, `na` (→ `1`); `or`, `money`, `f` in the link are ignored. One trailing dot on the host is allowed. No usable filter → HTML path (the unfiltered page is server-rendered). `sort=1` ("by date") is always added, so newest-first holds. Endpoint `GET https://geekjob.ru/json/find/vacancy?page=N&...` → `{page, nextpage, pagecount, documentsCount, data: [{id, position, company: {name}, log: {modify, archived}, ...}]}`, ≤ 100 items per page; `nextpage == 0` ends. Item → `ListingJob(url=https://geekjob.ru/vacancy/<id>, title=position)`; ids `[A-Za-z0-9]{1,64}` only, archived items and repeats skipped, ≤ 200 items per answer looked at. Company name is not passed (`ListingJob` not widened; the job page's JSON-LD has it).
- **`safe_http.fetch_json`**: same guard as `fetch_html` (address check per hop, pinned IP + SNI, manual redirects, 15 s / 5 MB, no cookies, `Accept-Encoding: identity`) with `Accept: application/json`, only `application/json` accepted; body parsed in a thread inside the same total time budget (past the deadline → `unreachable`); wrong type or invalid JSON (incl. too-deep nesting) → `PageFetchError("not_json")`. `fetch_html` still accepts HTML only (shared `_guarded_fetch` with per-call media types).
- **`blocked` reason**: on 403/429/503, `cf-mitigated: challenge` → `PageFetchError("blocked")`; also `server: cloudflare` on 403/503 whose first 16 KB contain `<title>Just a moment...</title>` or `/cdn-cgi/challenge-platform/`. Verified live: `careers.manychat.com/positions` → 403 + `cf-mitigated: challenge`. One text, `fetchers/errors.BLOCKED_MESSAGE` = "This site blocks automated readers", is used by the API (`SiteBlockedError` → 400 on preview, add, edit) and the worker (`READ_ERROR_MESSAGES["blocked"]`, Unavailable after 24 h as usual). Board APIs: `board_http.get_bytes` maps 403/429/503 + `cf-mitigated: challenge` to `BoardReadError("blocked")` (same text). Detail step: on a challenged job page every row due in this check for that source counts one failed read (no further requests; revision guard as usual), so a blocked site's backlog is rated by title after `WEB_DETAIL_MAX_ATTEMPTS` checks.

#### PR #39 pre-merge fixes

- **Ashby dates:** `job_posted_at` catches `OverflowError` from `astimezone` (`0001-01-01T00:00:00+01:00`, `9999-12-31T23:59:59-01:00`) → undated, so one hostile date no longer fails the whole board. `jobUrl` is stripped; a pasted board link with a `#fragment` is accepted (fragment dropped before the strict match).
- **Archived pages (geekjob):** `ListingPage.skipped_count` = entries skipped as archived/invalid on an adapter page with no usable entry. `read_listing` keeps paging past a page without new jobs only when `skipped_count > 0`; an empty page, an HTML page, or a page whose usable jobs were all filtered out by "Job link contains" ends the listing. The seen-key stop and the 5-page cap are unchanged. Preview of an adapter link reads up to `MAX_LISTING_PAGES` and stops at the first page with jobs (`read_web_listing(stop_at_first_jobs=True)`, same 15 s budget); HTML links still preview page 1 only.
- **Canonical geekjob URL:** `SiteListing.canonical_url` = `https://geekjob.ru/vacancies?<filters the adapter sends, fixed order, without money/sort>` (normalized). `vacancy_source_service.parse_input` replaces the parsed web URL with it, so add, preview and edit store and hash one URL per search; the edit no-op check also compares against `canonical_web_url(stored url)`. **No migration:** sources saved earlier keep their stored URL and hash and are read the same way (the adapter matches their URL); an equivalent edit is a no-op; only a new add of the same search is not matched against such an old row (rare; the user can remove one).
- **Redirects:** `SiteListing.max_redirects = 0`; the geekjob JSON request follows no redirect (a redirect → unreachable).
- **Parser failure:** an exception inside an adapter parser raises `PageFetchError("unreachable")` ("Could not open this page"), not an empty page ("No vacancies found").
- **Titles and texts:** one helper, `normalize.strip_invisible`, removes Unicode categories Cc, Cf and Cs (controls incl. C1 and NUL, zero-width and bidi characters, BOM, word joiners, tag characters, lone surrogates that cannot be UTF-8 encoded); tab/newline/CR are kept. Titles (geekjob `_clean_title`, `board_http.cap_name` for every board, `web_job` JSON-LD titles) use it fully; body text (`board_http.cap_text`, used by all boards and `web_job`) keeps Cf so emoji sequences survive. HTML listing titles come from bytes decoded with `errors="replace"` and cannot hold surrogates.
- **Ashby concurrency:** `vacancy_source_check.check_ashby_board` takes a per-loop `asyncio.Semaphore(1)` inside its 10 s budget and runs the read as its own task that releases the slot only when it ends, including its JSON parse thread. On timeout the user gets the error at once (shielded task keeps running), but the next check waits for the slot, so at most one Ashby parse thread runs at a time.
- **Known limitation (M4):** geekjob `sort=1` orders by last edit; an old job beyond the pages seeded at save that the employer edits moves to page 1 and arrives as new. The search answer has no creation date (`log.modify` only), so this cannot be fixed on our side.

---

## 3. Impact and Risk Analysis

- **System Dependencies:** spec 009 pipeline (evaluator, merge, alerts, retention, daily cap); `vacancy_card_sources` labels; the Groq budget (detail text replaces Telegram-length posts, same 1 500-char cut to the AI); third-party sites' markup.

- **Potential Risks & Mitigations:**

| Risk | Mitigation |
|---|---|
| SSRF to internal services / cloud metadata | `safe_http`: global-only addresses, pinned IP, every redirect re-checked, ports 80/443, size/time caps; hostile-input tests |
| DNS rebinding | Connect to the checked IP with Host/SNI; never a second lookup |
| XML bombs / external entities in RSS | `lxml` with entities and network disabled, `huge_tree=False`, 5 MB cap |
| JS-rendered or link-less sites (hirehi, avito, krisp) | Out of scope; preview says "No vacancies found…"; ATS hint offers the board when one is linked |
| Heuristic picks menu links | Optional `job_link_contains`; the AI rejects non-vacancies (spends daily cap, bounded by 30 details/check) |
| Listings not sorted newest first | Hint in the form; documented out of scope |
| Site blocks Jobbi (403, rate limits, ToS) | Low rate (≤ 35 requests/source/hour, 1 s pacing, one at a time per host); "Unavailable" after 24 h. `robots.txt` is not enforced in v1 (personal, low-volume use) — revisit for multi-user |
| Edit during a worker fetch | `revision` guard: stale results are dropped, the next check uses the new link |
| Edit during a first scan | `initial_attempt_started_at` lease → 409; stale lease ignored after 10 min |
| Detail pages never load | `detail_attempts` cap 3 → evaluated by title; no queue stall |
| Slow sites stretch the hourly check and block first scans (one shared job lock) | Listing stops at the first failed page; detail budget (3 consecutive failures / 5 min per source); 40-min cap on the web part of `check_all`; listing steps first; per-source duration logged |
| Stored XSS from scraped text | Plain text only (JSON-LD HTML and trafilatura output converted to text); React renders text |
| Prompt injection via page text | Same as spec 009: text fenced as data, validated output, no tools |

---

## 4. Testing Strategy

- **Backend unit (saved HTML/XML fixtures from the probed sites):**
  - `web_listing`: geekjob, ingamejob, hirify, ostrovok, careerspace pages → expected job links/titles; with and without `job_link_contains`; next-page detection (`rel=next`, `?page=N+1`); ATS hint on a Wrike-like page; hirehi-like page → zero jobs.
  - `web_job`: JobPosting (geekjob, yandex) → text, date, title, company; no JobPosting (ingamejob) → trafilatura text; HTML stripped.
  - `teamtailor`: RSS fixture → posts; malformed and entity-bomb XML rejected.
  - Normalization and key building; parsing order and every accepted/hostile input (look-alike hosts, `teamtailor.com.evil.com`, non-http schemes, 2 KB URL).
  - `safe_http` (respx + stubbed resolver): private/loopback/link-local/IPv4-mapped addresses rejected; redirect to a private IP rejected; redirect limit; non-HTML type; 5 MB cap; rebinding (resolver answers public then private) never connects to the private one.
- **Worker (respx, fixed clock, file-backed SQLite):** listing paging stops at a seen page and at 5; detail step cap 30 and order; retries and title fallback after 3; an exclude word found only in the job text drops the card; 404/410 job page drops the row with no AI call; detail step runs when the listing read failed and is skipped for users without a description; budget stops after 3 consecutive failures / 5 min and the 40-min web cap leaves work for the next check (slow-site stub); `waiting_count` excludes `needs_detail` rows; `no_vacancies` → Unavailable after 24 h and recovery; `revision` race drops stale results; teamtailor first scan (7 days) and hourly; web cards merge by `job_link` with other sources; AI title wins over listing title for web; no network inside a transaction (existing guard test extended).
- **API:** preview never writes and makes no network call for non-web kinds; save records every listed key (pages 1–5) and shows nothing new on the first check; duplicate by normalized URL; 30-source limit, and an edit or replace at exactly 30 sources succeeds; PATCH name / empty name → default; name > 100 → 400; web link edit keeps history and deletes the old filter's pending rows; Telegram link edit = replace with "(removed)" label showing the latest name (rename, then replace); `clever.com/careers` becomes a web source, `jobs.lever.co.evil.com` does not become Lever; 409 during an attempt; per-user isolation.
- **safe_http extras:** `HTTP_PROXY` set in the environment is ignored; NAT64 `64:ff9b::7f00:1` and IPv4-mapped `::ffff:127.0.0.1` rejected.
- **Frontend (Vitest + MSW):** preview flow (found / no vacancies / can't use / can't open), re-check with pattern, non-web kinds skip preview, ATS hint button, Edit modal for each kind (name only, web link, Telegram replace), disabled Edit that re-enables after a poll, cards show the new name right after a rename, "Watching since", focus handling.
- **Live check:** add a geekjob search, an ingamejob listing and a Teamtailor board; confirm previews; after a real new posting, a card appears within 2 hours; edit the geekjob filter; edit a Telegram channel; `http://localhost:8003/` is refused.
