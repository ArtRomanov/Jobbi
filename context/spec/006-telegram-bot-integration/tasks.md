# Tasks: Telegram Bot Integration

---

- [x] **Slice 1: Telegram linking backend**
  - [x] Create 3 new SQLAlchemy models: `TelegramLink`, `TelegramConnectionCode`, `TelegramConversation`. Create Alembic migration. **[Agent: database-expert]**
  - [x] Add `timezone` and `summary_time` columns to the `User` model. Update `UserRead` and `UserUpdate` schemas. Create Alembic migration. **[Agent: database-expert]**
  - [x] Create `telegram_service.py`: generate_code (6-char alphanumeric, 10-min expiry, single prior invalidation), verify_code (marks used, creates link), get_status, delete_link. **[Agent: python-backend]**
  - [x] Create `app/schemas/telegram.py` and `app/api/v1/telegram.py` with: `POST /telegram/connection-code`, `GET /telegram/status`, `DELETE /telegram/link`. Mount in v1 router. **[Agent: python-backend]**
  - [x] Verify: curl generate code → returns 6-char code. curl status → not connected. Manually insert link row → status shows connected. curl disconnect → link removed. PATCH /users/me with timezone + summary_time → persisted. **[Agent: qa-tester]**

---

- [ ] **Slice 2: Bot linking and dialog**
  - [ ] Add `python-telegram-bot[job-queue]>=21` to pyproject.toml. Add `TELEGRAM_BOT_TOKEN` and `JOBBI_PUBLIC_URL` to config.py Settings and .env.example. **[Agent: python-backend]**
  - [ ] Create `app/bot/` package: `__main__.py` entry point, `db.py` async session factory, `handlers/start.py` (code verification → create link), `handlers/cancel.py` (clear conversation). **[Agent: python-backend]**
  - [ ] Create `handlers/dialog.py`: message handler that starts/continues the create-application conversation, using the `telegram_conversations` table for state (awaiting_company → awaiting_role → awaiting_status → create application). **[Agent: python-backend]**
  - [ ] Add `bot` service to `docker-compose.yml` (shares backend image, runs `python -m app.bot`, same .env). **[Agent: devops-infra]**
  - [ ] Verify: Provide a real TELEGRAM_BOT_TOKEN, start bot service. Generate code via API, /start in Telegram, send code → bot confirms. Send a job URL → bot asks company → role → status → creates application. Verify application in DB. /cancel aborts dialog. **[Agent: qa-tester]**

---

- [ ] **Slice 3: Summary feature**
  - [ ] Create `summary_service.py` (backend): build summary text from applications (pipeline counts, recent status changes in last 24h, follow-up count for Applied > 7 days, empty state message). Shared by bot handlers and any future /summary API endpoint. **[Agent: python-backend]**
  - [ ] Create `handlers/summary.py`: `/summary` command → generate + send summary for the requesting chat. Returns "please link first" if unlinked. **[Agent: python-backend]**
  - [ ] Create `handlers/jobs.py`: on bot startup, register per-user daily JobQueue jobs at each user's summary_time in their timezone. Add a 5-minute refresh job that syncs registered jobs with current DB state (handles new links, changed times, disconnects). **[Agent: python-backend]**
  - [ ] Verify: /summary in Telegram → sends formatted summary message. Set summary_time to current time + 2 min, wait → summary arrives automatically. Empty state user gets "No applications tracked yet". **[Agent: qa-tester]**

---

- [ ] **Slice 4: Settings UI for Telegram**
  - [ ] Regenerate OpenAPI types. Create `entities/telegram/` slice: types, API calls (getTelegramStatus, generateConnectionCode, disconnectTelegram). **[Agent: typescript-frontend]**
  - [ ] Create `features/telegram-connect/` slice: `TelegramSection` component showing connection status. Not-connected state has "Connect Telegram" button that generates code and displays it with instructions. Connected state shows "@username" and "Disconnect" button with confirmation. Polls status every 3 seconds while code is displayed to detect when linking completes. **[Agent: typescript-frontend]**
  - [ ] Update `pages/settings/`: add `<TelegramSection />`. Add `timezone` and `summary_time` form fields. Auto-detect browser timezone via `Intl.DateTimeFormat().resolvedOptions().timeZone` on first mount if unset. **[Agent: typescript-frontend]**
  - [ ] Code review: Review polling pattern, connection flow UX, and FSD compliance. **[Agent: react-code-reviewer]**
  - [ ] Verify: Settings → Telegram section shows "Not connected". Click Connect → code displays. Complete link in Telegram → section auto-refreshes to "Connected as @username". Disconnect → back to not connected. Timezone detected and saved. **[Agent: qa-tester]**

---

- [ ] **Slice 5: Backend test suite for Telegram**
  - [ ] Telegram service tests: code generation (format, uniqueness per user, 10-min expiry), code verification (valid, expired, used, invalid), link CRUD. **[Agent: python-backend]**
  - [ ] API endpoint tests: connection-code (generates, invalidates prior), status (connected/not), disconnect, authorization. **[Agent: python-backend]**
  - [ ] User profile tests: timezone and summary_time accepted and returned by /users/me. **[Agent: python-backend]**
  - [ ] Summary service tests: pipeline counts, recent activity (24h window), follow-up count (Applied > 7 days), empty state. **[Agent: python-backend]**
  - [ ] Verify: `pytest` runs all tests — 100% pass rate. **[Agent: qa-tester]**

---

- [ ] **Slice 6: Frontend test suite for Telegram**
  - [ ] Add MSW handlers for `GET /telegram/status`, `POST /telegram/connection-code`, `DELETE /telegram/link`. **[Agent: typescript-frontend]**
  - [ ] TelegramSection tests: renders "Not connected" initially, click connect shows code, polling detects connection change, disconnect flow. **[Agent: typescript-frontend]**
  - [ ] Settings timezone/summary_time tests: fields visible, save sends values. **[Agent: typescript-frontend]**
  - [ ] Code review: Review test patterns and polling mocks. **[Agent: react-code-reviewer]**
  - [ ] Verify: `pnpm test` runs all tests — 100% pass rate. **[Agent: qa-tester]**
