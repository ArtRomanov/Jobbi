# Functional Specification: Switch LLM Vendor from Anthropic to Groq

- **Roadmap Item:** Follow-up change to "Claude Chat Integration" (Phase 2). Not a new roadmap item — this replaces the Anthropic-backed implementation behind the existing chat feature.
- **Status:** Completed
- **Author:** Poe (AI Product Analyst)

---

## 1. Overview and Rationale (The "Why")

The Claude Chat Integration was shipped on the Anthropic API, which charges prepaid credits separate from any Claude.ai or Claude Code subscription. Without those credits, every chat send fails (`credit balance is too low`) and the entire AI assistant feature is unreachable.

**Problem:** The user has no Anthropic API balance and prefers not to fund a separate per-token billing ledger for personal use. The chat feature — one of the four core product features — is currently unusable.

**Desired outcome:** The application's AI assistant runs on **Groq** instead of Anthropic. Groq's free tier is sufficient for personal use and unblocks all chat workflows. From the user's perspective, the chat works exactly as it did before — same page, same streaming, same quick actions, same persisted history. The Anthropic integration is removed entirely.

**Success criteria:**

- After the migration, the chat page works end-to-end with no Anthropic credentials configured anywhere in the system.
- All three quick actions (Refine CV, Cover Letter, Interview Prep) and free-form conversation produce useful responses on the first try.
- A user who has never used the previous Anthropic-backed chat cannot tell, from observing the UI, that anything changed about the AI assistant.

---

## 2. Functional Requirements (The "What")

### 2.1 Groq-Backed Chat

- **As a** user, **I want** the AI assistant to keep working exactly as it does today, **so that** I can continue refining CVs, drafting cover letters, and preparing for interviews without disruption.
  - **Acceptance Criteria:**
    - [x] The chat page (`/applications/:id/chat`) renders the same components, layout, and styling as before the migration.
    - [x] Sending a message produces a streamed assistant response in the same word-by-word manner as before.
    - [x] User and assistant message bubbles, timestamps, and ordering are unchanged.
    - [x] All three quick-action buttons (Refine CV, Cover Letter, Interview Prep) trigger the same prompts and produce useful responses.
    - [x] The system prompt continues to inject application context (company, role, job URL, notes, status) and linked CV content (personal info, summary, work experience, education, skills, languages), with the same context-awareness behavior described in spec 004 §2.3.
    - [x] Chat history is persisted identically — refreshing or returning to a conversation shows the full history.
    - [x] Existing chat messages stored before the migration remain readable in the conversation view; no history rewrite or migration is performed.
    - [x] Multi-line input, Enter-to-send, Shift+Enter for newline, and the clear-history action behave unchanged.

### 2.2 Configuration Migration

- **As an** operator, **I want to** configure the new vendor with a clear and minimal set of environment variables, **so that** setup is straightforward and there's no leftover Anthropic configuration to maintain.
  - **Acceptance Criteria:**
    - [x] A `GROQ_API_KEY` environment variable holds the Groq API key.
    - [x] A `GROQ_MODEL` environment variable selects which Groq model is used. The default value is `llama-3.3-70b-versatile`, applied when `GROQ_MODEL` is not set.
    - [x] The Anthropic-specific environment variables (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`) are removed from configuration templates and example files. Setting them has no effect.
    - [x] If `GROQ_API_KEY` is missing, the backend fails fast at startup with a clear error naming the missing variable.
    - [x] No code path in the backend, after the migration, calls the Anthropic API. The Anthropic SDK and any Anthropic-specific client code are removed from the codebase.

### 2.3 Failure Surfacing

- **As a** user, **I want** to see a clear error message when the AI assistant cannot respond, **so that** I understand what went wrong rather than seeing a broken or hung interface.
  - **Acceptance Criteria:**
    - [x] When Groq returns an error (rate limit, authentication failure, model unavailable, network timeout), the chat page surfaces the failure as an inline message in the conversation area.
    - [x] The error message includes the salient detail returned by the vendor (e.g., "Rate limit reached. Try again in a moment.") so the user knows what to do next.
    - [x] The user's just-sent message remains visible so they can retry by sending it again.
    - [x] After an error, the input is re-enabled so the user can compose another message immediately.

---

## 3. Scope and Boundaries

### In-Scope

- Replacing the LLM provider used by the application chat from Anthropic to Groq.
- Locking in `llama-3.3-70b-versatile` as the default Groq model, configurable via `GROQ_MODEL`.
- Configuration changes: introduce `GROQ_API_KEY` and `GROQ_MODEL`; remove `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` from configuration templates.
- Hard removal of the Anthropic integration: SDK dependency, client wrapper, and all Anthropic-specific code paths are deleted.
- Streaming responses, persisted history, quick-action buttons, and context-injection behavior all remain functionally equivalent to spec 004.
- Inline in-chat error messages when Groq returns an error.
- Backwards compatibility for viewing historical messages produced by the previous Anthropic backend (no data migration needed; messages are plain text).

### Out-of-Scope

- **Multi-vendor support** — only Groq is supported after the migration. There is no env-var toggle, UI selector, or fallback to another vendor.
- **User-facing vendor selection** — no settings page or per-conversation vendor choice.
- **Automatic fallback** — if Groq is unavailable, the user sees an error; the system does not silently retry on another vendor.
- **Vendor branding in the UI** — the chat does not display "powered by Groq" or any vendor label.
- **Re-running historical conversations through Groq** — past assistant responses produced by Anthropic are kept verbatim.
- **Prompt tuning specific to Groq** — system prompt and quick-action templates are kept as-is. Output quality differences from the previous Claude-backed responses are accepted.
- **Additional LLM vendors** — OpenAI, Gemini, Mistral, OpenRouter, Ollama, etc. are not in scope. Adding any of them would be a separate spec.
- **Cost tracking, token accounting, or usage metrics** — same as spec 004 §3 (Out-of-Scope).
- **Telegram bot AI usage** — the bot does not currently call any LLM; nothing changes there.
- **Other roadmap items:** User Account Essentials, Application Tracker, CV Constructor, Metrics Dashboard, Telegram/HeadHunter/LinkedIn integrations.
