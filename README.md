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
