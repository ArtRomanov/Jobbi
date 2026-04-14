# Functional Specification: Telegram Bot Integration

- **Roadmap Item:** Telegram Bot Integration (Phase 4 — Job Search Integrations V1.1)
- **Status:** Draft
- **Author:** Poe (AI Product Analyst)

---

## 1. Overview and Rationale (The "Why")

The user spends time in Telegram already — they get job leads there, chat with recruiters, and skim job channels. Forcing them to context-switch to Jobbi to log everything is friction.

**Problem:** There's no way to quickly capture a job opportunity the user finds in Telegram, and no way to stay informed about their Jobbi pipeline without opening the app.

**Desired outcome:** A Telegram bot linked to the user's Jobbi account that (1) lets them forward a job posting to create an application via an interactive conversation, and (2) sends a daily summary of their pipeline at 10:00 AM their local time so they can stay informed passively.

**Success criteria:**
- The user can link their Telegram to Jobbi in under 30 seconds.
- Creating an application from Telegram takes less than 60 seconds via bot dialog.
- The daily summary arrives reliably at 10:00 AM user local time.

---

## 2. Functional Requirements (The "What")

### 2.1 Linking Telegram to Jobbi

- **As a** user, **I want to** connect my Telegram account to Jobbi, **so that** the bot can create applications for me and send me updates.
  - **Acceptance Criteria:**
    - [ ] The Settings page has a new "Telegram" section showing the current connection status: "Not connected" or "Connected as @username".
    - [ ] When not connected, a "Connect Telegram" button generates a 6-digit connection code (expires after 10 minutes) and displays instructions: "Open @JobbiBot in Telegram, send /start, then send the code: ABC123".
    - [ ] The user opens Telegram, sends `/start` to the bot, and the bot asks for the code.
    - [ ] When the user sends a valid, unexpired code in Telegram, the bot links the user's Telegram chat_id to the Jobbi account and replies with a confirmation: "You're connected! You can now forward job postings to me or ask for /summary."
    - [ ] The Settings page refreshes to show "Connected as @username" with a "Disconnect" button.
    - [ ] The Settings page also has a "Daily summary time" field (defaults to 10:00) where the user can set the hour the summary is sent.
    - [ ] The user's timezone is required for scheduling — Settings detects browser timezone and saves it.
    - [ ] Clicking "Disconnect" removes the Telegram link from the account.

### 2.2 Quick Add Application from Telegram

- **As a** user, **I want to** create a job application by forwarding a message to the bot, **so that** I can capture opportunities without opening Jobbi.
  - **Acceptance Criteria:**
    - [ ] When the user sends any message (other than a command) to the linked bot, the bot starts an interactive conversation:
      1. Bot extracts any URL from the message and uses the message text as initial notes (stored in context).
      2. Bot asks: "Got it! What company is this for?"
      3. User replies with the company name.
      4. Bot asks: "What's the role/title?"
      5. User replies with the role title.
      6. Bot asks: "Which status? Reply with: researching, applied, interview, offer, rejected, withdrawn" (or shows inline keyboard buttons for these).
      7. User replies with a status.
      8. Bot creates the application via Jobbi's internal API and confirms: "✅ Application created: [Company] — [Role] ([Status]). View it at http://localhost:5173/dashboard".
    - [ ] If the user cancels with `/cancel` during the dialog, the bot discards the pending application.
    - [ ] Only linked users can create applications via the bot. Unknown chat_ids get: "Please link your account first by running /start and entering your code."

### 2.3 Daily Summary

- **As a** user, **I want to** receive a daily summary of my job search pipeline in Telegram, **so that** I stay aware of my progress without opening Jobbi.
  - **Acceptance Criteria:**
    - [ ] Every day at the user's configured summary time (default 10:00 in their local timezone), the bot sends a summary message.
    - [ ] The summary message contains:
      - **Pipeline**: "📊 Pipeline: X researching, Y applied, Z in interview, A offers, B rejected"
      - **Recent activity**: "🔄 X status changes in the last 24 hours" (or "None" if zero)
      - **Upcoming actions**: "⏭️ X applications need follow-up" (defined as applications in Applied status older than 7 days) — optional if empty
      - Link back to Jobbi dashboard
    - [ ] If the user has no applications, the summary says: "📭 No applications tracked yet. Add one to get started!"
    - [ ] Summaries are not sent if the user is not linked.
    - [ ] The user can request the summary on-demand by sending `/summary` to the bot at any time.

---

## 3. Scope and Boundaries

### In-Scope

- Shared Telegram bot instance (one bot for all Jobbi users)
- Long-polling architecture (no webhooks required)
- Account linking via 6-digit connection code flow
- Interactive bot dialog for creating applications (company → role → status → confirm)
- `/cancel` command to abort a dialog
- Daily summary sent at user-configured local time (default 10:00)
- On-demand `/summary` command
- User timezone stored in profile (for scheduling)
- Settings page section for Telegram connection management

### Out-of-Scope

- **User Account Essentials, Application Tracker, CV Constructor, Claude Chat, Metrics Dashboard** (all completed)
- **HeadHunter Integration** (separate roadmap item — Phase 4)
- **LinkedIn Integration** (separate roadmap item — Phase 4)
- Webhook-based updates (long polling only for V1)
- Watched keyword alerts on Telegram channels (deferred)
- Claude-powered extraction of job details from forwarded messages (future enhancement)
- Bot commands beyond `/start`, `/cancel`, `/summary`, and message-driven dialogs
- Multi-step editing of existing applications via the bot (create-only)
- File/document uploads to the bot
- Inline mode or sharing to the bot from other Telegram clients
- Per-channel alerts or subscription management
