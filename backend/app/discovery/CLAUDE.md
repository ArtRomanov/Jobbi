# Discovery worker (`python -m app.discovery`)

Hourly check of vacancy sources → Groq evaluation (exclude words are not applied since spec 012) → Inbox → Telegram alerts. Run one instance only.

- **Source kinds and fetchers** (`fetchers/`): `telegram` (`telegram.py`); `greenhouse` / `lever` / `lever_eu` / `teamtailor` via `board_scan.py` (`greenhouse.py`, `lever.py`, `teamtailor.py` — RSS through `lxml` with entities and network off); `web` via `web_scan.py` (`web_listing.py` parses a listing, `web_job.py` reads one job page).
- **Web = two steps.** Listing step: up to 5 pages, stops after the first page with a seen key; new jobs are stored `pending` + `needs_detail`. Detail step: up to 30 job pages per source per check (JSON-LD `JobPosting`, else `trafilatura.extract`); after 3 failed reads the row is evaluated by its listing title. The evaluator skips `needs_detail` rows.
- **safe_http rule:** every user-supplied URL (API preview/save/edit and the worker) goes through `fetchers/safe_http.py` (public IPs only, pinned IP, every redirect re-checked, 15 s / 5 MB caps). Never call `trafilatura.fetch_url` or a plain `httpx` client on such URLs — only `trafilatura.extract` on HTML already fetched by `safe_http`.
- **Seen-key formats** (`vacancy_seen_keys.external_key`): `tg:<channel>/<post_id>`, `gh:<token>/<id>`, `lever:<company>/<id>` (`lever_eu:` for EU), `tt:<subdomain>/<job_id>`, `web:<source_id>/<sha256(normalized job url)>` — keyed by source id, so history survives a link edit.
- **No network inside a DB transaction:** fetch first, then a short write transaction, then commit.
- **Revision guard:** `VacancySource.revision` grows on every edit that changes what is fetched. `_SourceRef` carries the revision it was loaded with; stores add `AND revision = :rev` (rowcount 0 → results dropped), and the detail step checks `_revision_unchanged` before each write.
- **First-scan lease:** `_take_initial_lease` sets `initial_attempt_started_at` before a first-scan attempt; `_release_initial_lease` clears it. While set, the API refuses edits with 409; a lease older than `ATTEMPT_LEASE_TTL` (10 min, e.g. a crashed worker) is ignored.
