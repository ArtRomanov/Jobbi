# Technical Specification: Digest Posts and Forwarded Posts

- **Functional Specification:** [functional-spec.md](functional-spec.md)
- **Status:** Completed
- **Author(s):** Poe (AI Architect)

---

## 1. High-Level Technical Approach

Everything stays inside the existing discovery pipeline (fetch → pending card → AI batch → apply verdicts); no new services or processes.

- The AI answer changes to **"variant B"**: per post, `vacancy_count` plus a list of **only the matching** vacancies (at most 20). Each vacancy points to its text by **line numbers**; the AI never retypes text.
- When applying verdicts, the worker turns one pending post into up to 20 cards, each with its own fragment, job link and fit.
- Forwarded posts lose the PR #35 "kept as low fit" rule; after rating, the worker replies to the forwarded message with the result.
- The AI window grows from 1,500 to 3,000 characters; cut posts are flagged and reported in the daily summary.
- Exclude words are hidden in the UI and no longer applied anywhere (stored data and API kept; full removal is backlog #12). *Update 2026-11-24: backlog #12 done: `prefilter.py`, the API `exclude` field and the `exclude_terms` column (migration `9e2b4d6f8a10`) are removed.*

---

## 2. Proposed Solution & Implementation Plan (The "How")

### 2.1 Data Model / Database Changes

One Alembic migration; standard SQLAlchemy types only (no SQLite-specific features).

| Table | Change | Purpose |
|---|---|---|
| `vacancies` | + `links` JSON, nullable: list of `[line, url]` | Non-Telegram links of a **pending** post with the line each sits on, to pick a job link per vacancy. NULL for rows created before the migration and for board jobs. |
| `vacancy_seen_keys` | + `cut_for_ai` Boolean, NOT NULL, default false | Set when an evaluated post was longer than the AI window; counted by the daily summary. |
| `forwarded_posts` (new) | `id`, `user_id` (FK users, cascade), `external_key`, `chat_id`, `message_id`, `created_at`, `reported_at` (nullable); UNIQUE (`user_id`, `external_key`) | Where to reply with the rating result and whether that reply was sent. Deleted by the daily cleanup 30 days after `created_at`. |

- Cards from a digest are **new** `vacancies` rows with `external_key = <post key>#<n>` (`n` = the vacancy's position in the AI answer, 1-based). The pending row of the post is deleted after the split (with its card sources).
- `vacancy_seen_keys` stays one row per **post**: a seen post never produces cards again (functional §2.1).
- `vacancy_search_settings.exclude_terms` is kept untouched.

### 2.2 Evaluator (`backend/app/discovery/evaluator.py`)

- **Window:** `MAX_POST_CHARS` 1,500 → **3,000**.
- **Batching by size:** a batch takes pending posts in the current order until their text (each capped at the window) reaches `BATCH_CHAR_BUDGET = 7,500` characters or 5 posts, whichever comes first (7,500 = today's maximum of 5 × 1,500, so tokens per call and the 45 s pause stay valid for the 8,000 TPM account limit). A post longer than the budget's remainder starts the next batch; one post is always allowed.
- **Numbered lines:** inside its fence each post's text is sent as `L1: …`, `L2: …` (lines of the windowed text; defang applied as today).
- **Answer per post:** `{key, is_vacancy, vacancy_count, match, fit, reason, company, title, vacancies: [{lines: [from, to], fit, reason, company, title}]}`.
  - `vacancy_count ≤ 1` (or missing) → today's top-level fields are used; `vacancies` is ignored. Link-only digests fall here.
  - `vacancy_count ≥ 2` → only `vacancies` (matching only, ≤ 20) is used; top-level `match`/`fit` are ignored.
- **Validation (pydantic, as today):** an item needs `1 ≤ from ≤ to ≤ number of lines` and a valid `fit`; invalid items are dropped, the rest kept. Items beyond 20 are discarded. A digest whose items are **all** invalid while `vacancies` is non-empty counts as a failed attempt (existing 3-attempt rule). An empty `vacancies` with `vacancy_count ≥ 2` is a valid "no match".
- **Prompt:** new DIGESTS section — what counts as one vacancy's lines (its heading and the lines describing it; shared intro/outro lines not included), list only matching vacancies, keep match/fit rules per vacancy, a post that only announces vacancies elsewhere is `vacancy_count ≤ 1`.
- `MAX_COMPLETION_TOKENS` stays 4,000; if the live smoke run hits `finish_reason=length`, raise to 6,000.

### 2.3 Links per line (`RawPost`, fetcher, forward handler)

- `RawPost` (`backend/app/discovery/types.py`) gets `links: tuple[PostLink, ...]` with `PostLink(line: int, url: str)`: http(s) links not on Telegram hosts, normalized (`normalize_url`), ≤ 2,048 chars, 1-based line of the stored plain text.
- `fetchers/telegram.py`: record each anchor's line while building the plain text; `job_link` stays "first link" for single posts.
- `bot/handlers/inbox_forward.py`: line from the entity offset in the text/caption.
- Boards: no links (jobs are always single).
- `_store_posts` / `store_forwarded_post` write `links` on the pending row.

### 2.4 Applying verdicts (`backend/app/discovery/service.py`)

- **Single post** (`vacancy_count ≤ 1`): unchanged (match → `new`; no match → deleted; repost merge and `_promote_earlier_pending` as today).
- **Digest** (`vacancy_count ≥ 2`), in the same short write transaction, per valid item:
  1. fragment = lines `from..to` of the stored text, joined;
  2. job link = first `links` entry whose line is within `from..to`, else none (`links` NULL → none);
  3. job link matches a visible card (`_merge_target`) → add this post's card sources to it (merge, no new card);
  4. otherwise insert a `new` card copying `user_id`, `source_id`, `url`, `posted_at`, `found_at`, `from_initial_scan`, `alert_handled_at` and the card sources of the pending row, with `title`/`company`/`fit`/`fit_reason` from the item and `text` = fragment.
  Then delete the pending row and its card sources; set `evaluated_at` (and `cut_for_ai`) on the post's seen key. Created card ids go to `new_card_ids` (the combined alert counts cards).
- **Exclude words:** the pre-filter call in `_store_posts` is removed (`prefilter.py` stays unused until backlog #12); `posts_excluded` is dropped from the run report.
- **Remove PR #35 leftovers:** `_keep_forwarded`, `NOT_A_MATCH_REASON`, `NOT_RATED_REASON`, `_PendingRow.forwarded`.

### 2.5 Forwarded posts

- `store_forwarded_post`: no merge at store time (merging now happens per vacancy after rating); writes the pending row (with `links`) and a `forwarded_posts` row in one transaction. `ALREADY_SEEN` path unchanged (incl. marking a waiting fetched card alert-handled).
- Bot replies (`inbox_forward.py`): texts from functional §2.2; `MERGED_MESSAGE` removed.
- **Result reply:** `_apply_evaluation` (and the "3 failed attempts" path) records, for each post that has a `forwarded_posts` row, an outcome in the run report: `matched(added, merged, total, first card)`, `none`, `not_vacancy` or `unratable`. After the run — next to the alerts, **outside any transaction** — the worker sends the functional §2.2 text with `reply_to_message_id`, then sets `reported_at`. A single forwarded vacancy merged into an existing card gets "<Role> — <Company> is already in your Inbox.". On `TelegramError` it logs and still sets `reported_at` (no retry loop). Requires the worker's bot (already used for alerts); without a token, outcomes are only logged.
- Forwarded cards keep `alert_handled_at = now` (copied to digest cards), so they never reach the combined alert.
- The per-minute run keeps rating forwarded posts on the first attempt only (PR #35 rule).
- Evaluation order (backlog #19): in the hourly run forwarded posts go first and never count toward the per-source cap (`PER_SOURCE_RUN_LIMIT`).

### 2.6 Cut-post alert

- When a post's text is longer than 3,000 characters at evaluation: WARNING log (`external_key`, length), `cut_for_ai = true` on its seen key, `posts_cut` in the run report.
- Daily summary (`backend/app/services/summary_service.py`): count the user's seen keys with `cut_for_ai` and `evaluated_at` in the last 24 h; when > 0 add the functional §2.1 line.

### 2.7 Frontend

- `features/manage-sources`: remove the exclude-words block from the search settings form (the form sends only the description; the API field stays for compatibility). Update the slice `CLAUDE.md`.
- No Inbox changes: a digest card's `text` is its fragment; "(forwarded)" exists.

### 2.8 Update 2026-11-24: pre-AI keyword filter

Functional §2.4. Goal: protect the Groq free tier (200k tokens/day) from noisy sources now that exclude words are gone.

- **Data** (migration `b5d8f1a3c7e9`, after `9e2b4d6f8a10`; standard types only): `vacancy_search_settings.keywords` JSON list (default `[]`), `keyword_filter_enabled` Boolean (default true); `vacancy_seen_keys.filtered_at` nullable datetime.
- **Matcher** (`backend/app/discovery/keyword_filter.py`, `keyword_matches(title, text, keywords)`): one cached case-insensitive regex; left word boundary `(?<!\w)` (Unicode, so Cyrillic works) only for keywords that start with a letter or digit (".net" matches "ASP.NET"), no right boundary; spaces/hyphens inside a keyword match `[\s\-]+`. Empty list → True.
- **Where it runs:** `service._apply_keyword_filter`, called by `evaluate_pending` before each user's `_UserEvaluation` (not for users in `forwarded_only`, i.e. the per-minute run). It looks at the user's `pending` rows that are not `needs_detail` (web rows are checked after the detail step, on their page text) and whose `external_key` has no `forwarded_posts` row. Non-matching rows are deleted by a DELETE that re-checks "no `forwarded_posts` row" (a forward recorded meanwhile keeps its post); only keys actually deleted get `filtered_at`; `RunReport.posts_filtered` (logged as `filtered=`). One short write transaction, no network. All source kinds go through the same point. Users without a description are not reached (`_users_with_pending`), so their posts stay pending as before.
- **Forwarding a skipped post:** `store_forwarded_post` clears `filtered_at` (conditional UPDATE) when the post has no card and stores it as a new pending post with its `forwarded_posts` row (outcome ADDED), so it is rated and replied to as usual.
- **Option A (chosen):** a filtered post keeps only its seen key, so it never returns, even when keywords change later. Cheap and simple; the cost is that a keyword added later does not recover posts skipped earlier. Option B (keep skipped rows and re-check them after a keyword change) is backlog #21; an AI-suggested keyword list is backlog #20.
- **API:** `VacancySearchSettingsRead` gets `keywords: list[str]` and `keyword_filter: bool`; `PATCH /api/v1/vacancy-search-settings` accepts both, partial (left out = unchanged, the `UNSET` pattern). `normalize_keywords` in `vacancy_source_service.py`: trim, collapse inner whitespace, lowercase, de-dupe keeping order; 1–64 characters each with at least one letter or digit, at most 50 → 400 ("Keywords must be 1–64 characters", "Keywords must contain a letter or a digit", "You can add up to 50 keywords"; normalisation stops at the 51st unique keyword); the raw list is capped at 200 items (422); wrong JSON types → 422 (`StrictStr`/`StrictBool`). `DiscoveryStatus.filtered_last_24h`: the user's seen keys with `filtered_at` in the last 24 h (`vacancy_service.discovery_status`).
- **Frontend** (`features/manage-sources`): Keywords chip list (`shared/ui/chip-input`), the switch, the matching hint and the 24 h counter; Save sends description + keywords + switch in one PATCH and shows the normalized values.
- **Tests:** matcher unit tests; migration test; worker tests in `tests/discovery/test_keyword_filter_service.py` (skip + `filtered_at` + no AI call, digest with one matching line, forwarded never filtered in both runs, switch off / empty list, `needs_detail` rows untouched then filtered by page text, board job kept by title, per user, `posts_filtered`); API tests for the settings shape, normalisation, limits and the counter; vitest for the form.
- **Backlog #19 (no migration):** (D) `VacancySourceRead.pending_count` = the user's `pending` rows per `source_id` (`needs_detail` excluded, same rule as `vacancy_service._count_waiting`; forwarded rows have no source), one grouped COUNT (`vacancy_source_service.pending_counts`) for GET /vacancy-sources, the same narrowed to one id for PATCH; the panel shows "Waiting for AI: N" when N > 0 and `mergePolledSources` refreshes it. (E) `service._expire_stale_pending` runs right before `_apply_keyword_filter` with the same conditions (hourly run only; not `needs_detail`; no `forwarded_posts` row, re-checked in the DELETE): rows older than `STALE_PENDING_AFTER` (= `LOOKBACK`, 7 days) by `posted_at` for `tg:` keys or by `found_at` for any key (board/web `posted_at` is the employer's date, can be old for a job just found) are deleted with their card sources; seen keys stay without a marker; `RunReport.posts_expired` (logged as `expired=`). Tests: `tests/discovery/test_stale_pending_service.py`, API tests in `test_vacancy_sources_api.py`.

---

## 3. Impact and Risk Analysis

**System dependencies:** discovery worker (evaluator, service, fetcher, cleanup, alerts), bot process (forward handler), daily summary, manage-sources UI. Specs 009 and the PR #35 behaviour are amended (pointers in 009).

| Risk | Mitigation |
|---|---|
| Groq 8,000 TPM limit | Batches sized by characters (7,500 max = today's maximum); 45 s pause unchanged |
| AI returns wrong line numbers | Ranges validated against the post's lines; text and links always come from our stored copy; invalid items dropped; all-invalid → retry (max 3) |
| Prompt injection via digest text | Fence + defang unchanged; output is numbers, enums and a short reason; a fragment can only be a slice of the post |
| Card / alert flood | ≤ 20 cards per post; combined alert already shows 10 lines + "+M more" |
| Vacancies missed at the end of long posts | 3,000 window + daily ✂️ line; raise the window if it shows up often |
| Pending rows from before the migration | `links` NULL → digest cards get no job link ("Add to tracker" falls back to the post link) |
| Worker crashes between commit and the forward reply | Reply is lost, cards stay; accepted |
| Shared SQLite file | Unchanged rule: no network I/O inside a transaction |
| Exclude words silently stop working | Intended (functional §2.1); stored words kept for backlog #12 |
| Keyword filter skips a relevant post (2026-11-24) | Inclusive matching at a word start (one line keeps a digest); forwarded posts never filtered; switch off / empty list restores today's behaviour; the 24 h counter shows how much is skipped |

---

## 4. Testing Strategy

- **Evaluator unit tests:** parsing variant B (`vacancy_count`, items, invalid ranges, > 20 items, all-invalid → attempt, empty list = no match); numbered lines and defang; size-based batching (long post alone, budget respected).
- **Service tests** (FakeGroq extended to answer digests): split into N cards (fragment, job link by line, `#n` keys, copied fields); merge into an existing card; no exclude filtering; daily cap counts the post once; alerts count cards; `cut_for_ai` + `posts_cut`.
- **Forward tests:** new reply texts; `forwarded_posts` row; result reply per outcome via FakeBot (`reply_to_message_id`, `reported_at`), incl. "already in your Inbox"; no low-fit card.
- **Daily summary:** ✂️ line only when N > 0.
- **Frontend:** search settings form without exclude words (vitest).
- **Behavioural AI check (pre-merge gate):** add the functional reference digests and the real "100% remote jobs 18 Nov" post to `backend/scripts/smoke_evaluator.py`; run live on `gpt-oss-20b`.
- **Live test:** forward a new digest from a private channel; check the cards, their fragments and links, and the second bot message.
