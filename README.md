# Jobbi

Local-only job-hunting assistant: FastAPI backend (SQLite), React + Vite frontend, plus two background services.

## Running locally

```bash
cp .env.example .env        # then fill in the keys
docker compose up -d backend frontend
```

- API: http://localhost:8003
- UI: http://localhost:5174

## Database migrations

Migrations are **not** applied automatically — nothing in the images or Compose runs Alembic. Apply them after pulling new code and **before** starting `bot` or `discovery`:

```bash
# Docker (the backend container has the alembic/ folder and alembic.ini mounted)
docker compose up -d backend
docker compose exec backend alembic upgrade head

# Without Docker
cd backend && alembic upgrade head
```

After pulling spec 010 (web page sources), run `alembic upgrade head` — it adds 4 migrations (`4e7a1c9b2d05`, `b8d3f5a1c6e2`, `c4e9a2f7d1b3`, `d7a1e3b9f2c4`) — and rebuild the image, because of the new `trafilatura` / `lxml` dependency:

```bash
docker compose build backend bot discovery
```

## Background services

| Service     | Command                   | What it does                                                      |
|-------------|---------------------------|-------------------------------------------------------------------|
| `bot`       | `python -m app.bot`       | Telegram bot (polling).                                           |
| `discovery` | `python -m app.discovery` | Hourly vacancy discovery: reads sources, evaluates posts via Groq, fills the Inbox, sends Telegram alerts. |

Both use the backend image, the same `.env`, and the shared `backend-data` volume (SQLite file), and wait for `backend` to be healthy.

```bash
docker compose exec backend alembic upgrade head   # first, see above
docker compose up -d bot discovery
```

**Run exactly one `discovery` instance.** Do not use `docker compose up --scale discovery=N` and do not run `python -m app.discovery` locally while the container is up — two workers would fetch and evaluate the same posts twice, burn the Groq quota, and send duplicate alerts.

### Discovery settings (`.env`)

| Variable                     | Default            | Meaning                                                                 |
|------------------------------|--------------------|-------------------------------------------------------------------------|
| `GROQ_DISCOVERY_MODEL`       | `qwen/qwen3.8-27b` | Groq model used to evaluate posts (chat uses `GROQ_MODEL`).             |
| `DISCOVERY_DAILY_EVAL_LIMIT` | `150`              | Max posts evaluated per user per local day. Sized for the shared Groq free-tier budget; raise only with a bigger plan. |

`GROQ_API_KEY` is required for evaluation; `TELEGRAM_BOT_TOKEN` is optional (without it, no alerts are sent).

## Vacancy sources

Add sources in Inbox → Sources by pasting a link. Supported:

| Source                  | Link                                                         |
|-------------------------|--------------------------------------------------------------|
| Telegram public channel | `@name` or `t.me/name`                                       |
| Greenhouse / Lever      | the board link                                               |
| Teamtailor              | `<company>.teamtailor.com` (not a company's own domain)      |
| Web page                | any other `http(s)` link: an aggregator search or a career page |

**Adding a web page:**

1. Open the site, set its own filters (e.g. `?q=react&remote=1`) and **sort by newest first** — Jobbi looks for new vacancies at the top of the list.
2. Paste the link and press Add. A preview shows "Found N vacancies" and the first 5 titles.
3. If the titles look like menu items, fill **"Job link contains"** (e.g. `/vacancy/`) and Re-check.
4. If the page links to a Greenhouse, Lever or Teamtailor board, the preview offers "Add the board" — prefer it: full job texts and dates.
5. Save. Vacancies already listed are marked as seen; only new ones reach the Inbox.

**Doesn't work:** pages that render vacancies with JavaScript ("No vacancies found"), sites behind a login or captcha, listings not sorted newest first (a new vacancy below seen ones can be missed), local/private addresses ("This link can't be used").

**Limits:** per source per hourly check — up to 5 listing pages and 30 job pages opened; the rest waits for the next check. The daily AI limit (`DISCOVERY_DAILY_EVAL_LIMIT`, 150) is shared by all sources.

**Edit:** every source has Edit (disabled while its first scan runs).
- Name only → applied at once; an empty name falls back to the default (domain, channel or board name).
- Web page link or "Job link contains" → preview again; history is kept, what is listed now counts as seen, existing cards stay.
- Telegram / board link (or a switch to another kind) → works like remove + add: old cards stay under "<old name> (removed)", the new source gets the normal 7-day first scan.
