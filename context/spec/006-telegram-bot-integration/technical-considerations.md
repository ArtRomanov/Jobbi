<!--
This document describes HOW to build the feature at an architectural level.
It is NOT a copy-paste implementation guide.
-->

# Technical Specification: Telegram Bot Integration

- **Functional Specification:** `context/spec/006-telegram-bot-integration/functional-spec.md`
- **Status:** Completed
- **Author(s):** Poe (AI Technical Architect)

---

## 1. High-Level Technical Approach

This feature adds a Telegram bot as a **separate long-polling worker process** that shares the Jobbi database. The bot uses `python-telegram-bot` (PTB) with its built-in `JobQueue` for scheduling daily summaries and persists conversation state in a new `telegram_conversations` table.

A new backend table `telegram_links` maps Jobbi users to Telegram chat_ids. Connection codes are short-lived tokens stored in a new `telegram_connection_codes` table. The user profile gets two new fields: `timezone` (IANA timezone string) and `summary_time` (HH:MM string).

**Systems affected:**
- Backend: 3 new tables, connection code endpoint, user profile updates, bot service
- Frontend: Settings page gets a Telegram section
- Infrastructure: New `bot` service in Docker Compose

**Deployment note:** The bot is **user-provided** — each Jobbi instance uses its own bot token, set via `TELEGRAM_BOT_TOKEN` env var. The user creates the bot via @BotFather before first run.

---

## 2. Proposed Solution & Implementation Plan

### 2.1 Data Model / Database Changes

**Table: `telegram_links`** — One row per linked user

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID (String 36) | PK | |
| `user_id` | UUID (String 36) | FK → users.id, UNIQUE, NOT NULL | One link per user |
| `chat_id` | BIGINT | UNIQUE, NOT NULL, indexed | Telegram chat id |
| `telegram_username` | VARCHAR(64) | NULLABLE | For display ("Connected as @username") |
| `linked_at` | DATETIME | NOT NULL | server_default |

**Table: `telegram_connection_codes`** — Short-lived linking tokens

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID (String 36) | PK | |
| `user_id` | UUID (String 36) | FK → users.id, NOT NULL, indexed | |
| `code` | VARCHAR(6) | NOT NULL, indexed | 6-digit alphanumeric (uppercase letters + digits) |
| `expires_at` | DATETIME | NOT NULL | Created + 10 minutes |
| `used_at` | DATETIME | NULLABLE | Set when consumed, prevents reuse |

**Table: `telegram_conversations`** — In-progress dialog state

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `chat_id` | BIGINT | PK | One active conversation per chat |
| `step` | VARCHAR(32) | NOT NULL | Enum: `awaiting_company`, `awaiting_role`, `awaiting_status` |
| `context_data` | JSON | NULLABLE | Partial application data being assembled (initial_notes, url, company, role) |
| `updated_at` | DATETIME | NOT NULL | server_default, onupdate |

**Users table additions:**

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `timezone` | VARCHAR(64) | NULLABLE | IANA timezone (e.g., "Europe/Berlin"). Default NULL — treated as UTC until set. |
| `summary_time` | VARCHAR(5) | NOT NULL, default "10:00" | HH:MM format |

**Migrations:** Two Alembic migrations:
1. Create `telegram_links`, `telegram_connection_codes`, `telegram_conversations` tables
2. Add `timezone` and `summary_time` columns to `users` table

### 2.2 API Contracts

All require JWT unless noted.

**`POST /api/v1/telegram/connection-code`** — Generate a new connection code
- Success (201): `{ code: "ABC123", expires_at: "2026-..." }`
- Invalidates any prior active code for the user

**`GET /api/v1/telegram/status`** — Check connection status
- Success (200): `{ connected: bool, telegram_username: string | null, linked_at: string | null }`

**`DELETE /api/v1/telegram/link`** — Disconnect Telegram
- Success (200): `{ message: "Disconnected." }`

**`PATCH /api/v1/users/me`** — Extended to accept `timezone` and `summary_time` fields
- Existing endpoint, no URL change
- Schema updated: `UserUpdate` adds optional `timezone` and `summary_time` fields

**`GET /api/v1/users/me`** — Returns `timezone` and `summary_time` in response
- Existing endpoint, schema extended

### 2.3 Backend Components

| Path | Responsibility |
|---|---|
| `backend/app/models/telegram_link.py` | `TelegramLink` SQLAlchemy model |
| `backend/app/models/telegram_connection_code.py` | `TelegramConnectionCode` model |
| `backend/app/models/telegram_conversation.py` | `TelegramConversation` model |
| `backend/app/schemas/telegram.py` | Pydantic schemas: `ConnectionCodeResponse`, `TelegramStatus` |
| `backend/app/services/telegram_service.py` | Business logic: generate code, verify code, create link, delete link, conversation state CRUD |
| `backend/app/services/summary_service.py` | Build daily summary text from application data (shared between bot and /summary command) |
| `backend/app/api/v1/telegram.py` | Route handlers for connection-code, status, disconnect endpoints |

Modified:
| Path | Change |
|---|---|
| `backend/app/models/user.py` | Add `timezone` and `summary_time` columns |
| `backend/app/schemas/user.py` | Add fields to `UserRead` and `UserUpdate` |

### 2.4 Bot Service (Separate Process)

New directory: `backend/app/bot/`

| Path | Responsibility |
|---|---|
| `backend/app/bot/__main__.py` | Entry point: `python -m app.bot` starts the bot polling loop |
| `backend/app/bot/handlers/start.py` | `/start` command handler and connection code verification |
| `backend/app/bot/handlers/cancel.py` | `/cancel` command handler |
| `backend/app/bot/handlers/summary.py` | `/summary` command handler |
| `backend/app/bot/handlers/dialog.py` | Message handler for non-command messages (drives the create-application dialog) |
| `backend/app/bot/handlers/jobs.py` | JobQueue setup: register per-user daily summary jobs on bot start |
| `backend/app/bot/db.py` | Standalone async DB session factory for the bot process (reuses `app.core.database` config) |

**Conversation flow (state machine):**
```
(no state) → user sends message → extract URL/notes → state = awaiting_company
awaiting_company → user replies company → state = awaiting_role
awaiting_role → user replies role → state = awaiting_status (inline keyboard)
awaiting_status → user taps button → create application → clear state → confirm
any state → /cancel → clear state → "Cancelled"
```

Conversation state is persisted in `telegram_conversations` table (keyed by chat_id), surviving bot restarts.

**JobQueue scheduling:**
- On bot startup, load all `telegram_links`, and for each linked user with a `timezone` set, register a daily job at `summary_time` in that timezone.
- When a user connects/disconnects or changes their `summary_time`/`timezone`, the corresponding job is updated. This requires a simple polling refresh every 5 minutes (or a pub-sub mechanism — use polling for V1 simplicity).

### 2.5 Frontend Components (FSD)

| Layer/Slice | Path | Content |
|---|---|---|
| `entities/telegram` | `frontend/src/entities/telegram/` | Types from OpenAPI, API calls: `getTelegramStatus()`, `generateConnectionCode()`, `disconnectTelegram()` |
| `features/telegram-connect` | `frontend/src/features/telegram-connect/` | `TelegramSection` component for the settings page: shows status, connect/disconnect flow with code display |
| `pages/settings` | `frontend/src/pages/settings/` | Existing page — add `<TelegramSection />` + fields for `timezone` and `summary_time` |

### 2.6 Frontend Dependencies

No new libraries. Timezone detection uses built-in `Intl.DateTimeFormat().resolvedOptions().timeZone`.

### 2.7 Configuration

| Env Variable | Purpose | Example |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | `1234567:ABC-DEF...` |
| `JOBBI_PUBLIC_URL` | URL used in bot messages to link back to the dashboard | `http://localhost:5173` |

Add to `.env.example`, `core/config.py` Settings, and the bot service in `docker-compose.yml`.

### 2.8 Docker Compose Changes

Add a new service:
```yaml
bot:
  build:
    context: ./backend
    target: production
  command: python -m app.bot
  env_file:
    - .env
  volumes:
    - ./backend/app:/app/app
    - backend-data:/app/data
  depends_on:
    backend:
      condition: service_healthy
```

### 2.9 Dependencies

**Backend:**
- `python-telegram-bot[job-queue]` ≥ 21 — Telegram bot framework with JobQueue
- `pytz` or rely on `zoneinfo` (stdlib) for timezone handling

---

## 3. Impact and Risk Analysis

**System Dependencies:**
- Requires a Telegram bot token (external — user must create via @BotFather)
- Shared database means bot and backend must coordinate on schema (handled by shared models)

**Potential Risks & Mitigations:**

| Risk | Impact | Mitigation |
|---|---|---|
| Missing `TELEGRAM_BOT_TOKEN` | Bot service fails to start | Docker service logs clear error. Other services run fine. |
| Bot restart loses in-memory state | User's dialog is interrupted | Conversation state in DB → state survives restarts. |
| Timezone handling errors | Summary sent at wrong time | Use `zoneinfo` (stdlib Python 3.9+). Default to UTC if timezone unset. |
| Connection code brute force | Unauthorized account linking | Codes are 6 chars (alphanumeric uppercase) = ~2B combos; expire in 10 min; single-use. |
| Multiple users linking same chat_id | Account hijacking | `chat_id` is UNIQUE in `telegram_links`. Linking a chat already linked to another user fails with clear message. |
| Bot polling hits rate limits | Delayed messages | PTB handles Telegram rate limits automatically. Fine for single-user personal use. |
| DB schema coupling | Bot and backend must update together | Both use shared SQLAlchemy models from `app.models`. Migrations run on backend; bot restarts to pick up new schema. |

---

## 4. Testing Strategy

**Backend (pytest):**
- Connection code generation, expiry, single-use validation
- Link/unlink user (telegram_links CRUD)
- Status endpoint (connected vs not)
- User profile updates accept `timezone` and `summary_time`
- Authorization: can't disconnect other users' links

**Bot (pytest with mocked PTB Application):**
- `/start` + code flow creates a link
- `/start` with invalid/expired code returns appropriate error
- Non-command message starts dialog → saves conversation state
- Dialog progression: company → role → status → creates application
- `/cancel` clears conversation state
- `/summary` generates correct summary text (mock application data)
- Unknown chat_id gets "please link first" message

**Summary service (pytest):**
- Pipeline counts correct
- Recent activity count (last 24h)
- Follow-up count (Applied > 7 days old)
- Empty state message when user has no applications

**Frontend (Vitest + Testing Library):**
- Telegram section shows "Not connected" initially
- Connect flow generates code, displays it with instructions
- Status polling updates to "Connected as @username"
- Disconnect clears status
- Settings form saves timezone + summary_time
