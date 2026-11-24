# System Architecture Overview: Jobbi

---

## 1. Application & Technology Stack

- **Frontend Framework:** React + Vite (TypeScript)
- **Backend Framework:** Python + FastAPI
- **ORM:** SQLAlchemy (standard patterns only — no SQLite-specific features, to keep PostgreSQL migration trivial)
- **API Style:** RESTful JSON API
- **Language Standards:** TypeScript (frontend), Python 3.11+ (backend)

---

## 2. Data & Persistence

- **Primary Database:** SQLite (via SQLAlchemy ORM)
- **Migration Tool:** Alembic (SQLAlchemy's migration companion)
- **Caching:** None for V1 (single-user app, direct DB queries are sufficient)
- **File Storage:** Local filesystem (for CV document storage)

> **Note:** SQLite chosen for simplicity. The ORM abstraction ensures a straightforward migration path to PostgreSQL if needed. All database interactions must use standard SQLAlchemy patterns — avoid SQLite-specific features.

---

## 3. Infrastructure & Deployment

- **Deployment Target:** Local only (V1)
- **Local Development:** Docker Compose with four services: `backend` (FastAPI), `frontend` (Vite), `bot` (`python -m app.bot`, Telegram bot) and `discovery` (`python -m app.discovery`, vacancy discovery worker). `bot` and `discovery` reuse the backend image and share the SQLite volume.
- **Containerization:** Docker (one container per service)
- **Background Jobs:** APScheduler 3.x (`AsyncIOScheduler`) inside the long-running `bot` and `discovery` processes; no separate queue or broker. The discovery worker runs an hourly `check_all` over all sources, every-minute first scans of newly added sources (last 7 days) and a daily cleanup at 03:30 UTC; jobs share one lock (`max_instances=1`). Run exactly one discovery worker: alerts are not deduplicated across instances.
- **Network rule for workers:** no network I/O inside a database transaction (read → network → short write).
- **Future Deployment:** TBD — Docker-based setup makes migration to VPS or cloud straightforward

---

## 4. External Services & APIs

- **Authentication:** Simple email + password (hashed with bcrypt, JWT tokens for session management)
- **AI Integration:** Groq API (direct HTTPS calls via official Python SDK). Three models, set by env:
  - `GROQ_MODEL` — AI chat (CV tailoring, tool edits): `qwen/qwen3.8-27b`.
  - `GROQ_DISCOVERY_MODEL` — vacancy evaluation: `openai/gpt-oss-20b` with `reasoning_effort=medium`, JSON mode, batches of up to 5 posts, at most one call per 45 s (account limit 8 000 tokens/min), up to 150 posts per user per day. Untrusted post text is fenced as data in the prompt.
  - `GROQ_DISCOVERY_FALLBACK_MODEL` — vacancy evaluation while the discovery model is out of its daily quota: `openai/gpt-oss-120b` (same family: same prompt, JSON mode and `reasoning_effort=medium`). Groq counts tokens per day (TPD, 200 000 on the free tier, rolling 24 h) per model, so the fallback doubles the daily budget. Only a daily 429 (TPD/RPD in the message) switches models; the worker remembers until Groq's "try again in …" time that the primary is out and sends later batches straight to the fallback. A per-minute 429 (TPM/RPM), or a daily 429 on both models, stops the run as before. Never the chat model (it would spend the chat's quota; the worker warns at startup if it is). A wait is capped at 24 h; an unknown fallback name (404 `model_not_found`) logs one error and turns the fallback off until restart. Empty disables it. The per-user daily cap counts posts rated by either model.
- **Vacancy Sources (discovery worker):** public Telegram channels via the `t.me/s/<channel>` web preview (HTML, BeautifulSoup); Greenhouse job boards (`boards-api.greenhouse.io`) and Lever (`api.lever.co`, EU: `api.eu.lever.co`) JSON APIs. Fixed hosts only, no redirects, 5 MB response cap.
- **Telegram Bot:** `python-telegram-bot` with `TELEGRAM_BOT_TOKEN`; the same token sends daily summaries, quick add and vacancy alerts (one grouped message per user per hourly check).
- **API Key Management:** Environment variables (`.env` file, not committed to source control)

---

## 5. Observability & Monitoring

- **Logging:** Structured JSON logging (Python `structlog` or `python-json-logger`)
- **Error Tracking:** Sentry (captures unhandled exceptions and error context)
- **Metrics:** None for V1 (application-level metrics dashboard covers user-facing stats)