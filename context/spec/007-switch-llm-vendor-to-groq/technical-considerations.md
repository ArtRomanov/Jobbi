# Technical Specification: Switch LLM Vendor from Anthropic to Groq

- **Functional Specification:** [`functional-spec.md`](./functional-spec.md)
- **Status:** Completed
- **Author(s):** Architect (AI)

---

## 1. High-Level Technical Approach

The chat feature today calls Anthropic via the `anthropic` Python SDK from a single backend module (`app/services/claude_client.py`), invoked from `app/services/chat_service.py`. The HTTP layer (SSE streaming endpoint) and the entire frontend are vendor-agnostic — they only see opaque text chunks framed as SSE events.

The migration therefore reduces to a localized backend swap:

1. Replace the `anthropic` SDK with the official **`groq`** Python SDK (vendor-native, async-first, OpenAI-shaped API).
2. Rename the client wrapper module to reflect its new responsibility and rewrite its body to call Groq.
3. Update settings, environment templates, and the architecture doc to reflect Groq as the LLM provider.
4. Update the chat service to pass system prompts using OpenAI-compatible message shape (system message inside the `messages` array rather than as a top-level argument).
5. Adapt unit tests that referenced Anthropic-named symbols.

No database migration, no schema change, no frontend change, no SSE protocol change. Existing chat history rows remain valid plain text.

The Groq Python SDK reference is at https://github.com/groq/groq-python; the OpenAI-compatible chat-completions semantics are documented at https://console.groq.com/docs/api-reference#chat. Default model is `llama-3.3-70b-versatile` per the functional spec.

---

## 2. Proposed Solution & Implementation Plan (The "How")

### 2.1 Architecture Changes

The "External Services & APIs" section of `context/product/architecture.md` currently states:

> AI Integration: Anthropic API (direct HTTPS calls via official Python SDK)

This must be updated as part of the implementation to:

> AI Integration: Groq API (direct HTTPS calls via official Python SDK)

No new services, no new infrastructure. The single existing LLM call site stays the only one.

### 2.2 Dependency Changes

`backend/pyproject.toml`:

| Action | Package | Notes |
|---|---|---|
| Remove | `anthropic>=0.40,<1` | No longer used. |
| Add | `groq>=0.13,<1` | Official Groq Python SDK; latest minor in the `0.x` line is acceptable. Verify exact bound at install time against https://pypi.org/project/groq/. |

Lockfile / installed environment must be refreshed (`pip install -e ".[dev]"` inside the backend container or local venv).

### 2.3 Configuration Changes

| File | Change |
|---|---|
| `backend/app/core/config.py` | Remove `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` fields. Add `GROQ_API_KEY: str = ""` and `GROQ_MODEL: str = "llama-3.3-70b-versatile"`. Add a startup validator (or rely on the existing `Settings.SECRET_KEY` pattern) that rejects an empty `GROQ_API_KEY` before the app accepts traffic. |
| `.env` | Remove `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`. Add `GROQ_API_KEY=...`, optional `GROQ_MODEL=llama-3.3-70b-versatile`. |
| `.env.example` | Same change as `.env` (template parity). |

The fail-fast behavior required by FR §2.2 is achieved by raising at the first call site if `GROQ_API_KEY` is empty (a Pydantic validator on the `Settings` model is cleanest — `model_validator(mode="after")` checking `GROQ_API_KEY` is non-empty when the chat code path is reachable).

### 2.4 Module Rename and Rewrite

| Path | Action | Responsibility |
|---|---|---|
| `backend/app/services/claude_client.py` | **Delete** | Anthropic-specific wrapper. |
| `backend/app/services/groq_client.py` | **Create** | Groq-specific wrapper. Owns the `groq.AsyncGroq` client construction, exposes `build_system_prompt(application, cv)` and `stream_llm_response(system_prompt, messages)`. |

The new module's public surface intentionally mirrors the old one's, with one rename: `stream_claude_response` → `stream_llm_response`. `build_system_prompt` is content-only and moves over unchanged.

#### `stream_llm_response` contract

```
async def stream_llm_response(
    system_prompt: str,
    messages: list[dict[str, str]],   # [{"role": "user"|"assistant", "content": str}, ...]
) -> AsyncIterator[str]:
    ...
```

Internally:
- Constructs the Groq message list as `[{"role": "system", "content": system_prompt}, *messages]` (system goes inside the array for OpenAI-compatible APIs, unlike Anthropic where it's a top-level kwarg).
- Calls `client.chat.completions.create(model=settings.GROQ_MODEL, messages=..., stream=True, max_tokens=4096)`.
- Iterates the async stream, yielding `chunk.choices[0].delta.content` when present (skipping `None` deltas — the first chunk typically has no content).
- Wraps `groq.APIError` (and subclasses such as `RateLimitError`, `AuthenticationError`) in the same `raise` pattern as today, so the SSE error frame in `chat.py:send_message` continues to surface them.

### 2.5 Chat Service Updates

`backend/app/services/chat_service.py`:

- Update the import: `from app.services.groq_client import build_system_prompt, stream_llm_response`.
- Update the function call: `async for chunk in stream_llm_response(system_prompt, messages):`.
- No other changes — message persistence, history loading, system-prompt construction, and the user/assistant write paths remain identical.

### 2.6 API and Frontend

No changes. The streaming endpoint at `POST /api/v1/applications/{application_id}/chat` continues to emit SSE frames `event: token` / `event: done` / `event: error` with the same JSON payload shape. The frontend SSE consumer in `frontend/src/entities/chat/api/send-message.ts` is untouched.

### 2.7 Error Mapping

The functional spec requires user-friendly error detail. The simplest approach: let `groq` SDK exceptions propagate; the `chat.py:send_message` wrapper already serializes `str(e)` into the SSE error frame. The Groq SDK's default exception messages are descriptive enough (e.g., `"Rate limit reached for model 'llama-3.3-70b-versatile' in organization … Please try again in 16.234s."`).

If the raw SDK message is judged too noisy at QA time, a small mapping helper can be added:

| Exception class | User-facing message |
|---|---|
| `groq.AuthenticationError` | "AI service authentication failed. Please contact the operator." |
| `groq.RateLimitError` | "Rate limit reached. Please try again in a moment." |
| `groq.APIConnectionError` | "Couldn't reach the AI service. Please try again." |
| `groq.APIStatusError` (other) | The SDK's own message. |

This mapping is a follow-up optimization, not a launch blocker.

### 2.8 Test Updates

`backend/tests/test_chat.py`:

- Update import: `from app.services.groq_client import build_system_prompt`.
- Update the two `monkeypatch.setattr` strings from `app.services.chat_service.stream_claude_response` to `app.services.chat_service.stream_llm_response`.
- The test fixtures that yield fake stream chunks remain valid (they're plain async generators of strings, vendor-agnostic).

No test case logic changes; this is purely a name swap.

---

## 3. Impact and Risk Analysis

### System Dependencies

- **Backend startup** depends on `GROQ_API_KEY` being present in the environment. Documented as a required env var in both `.env.example` and the docker-compose flow.
- **Frontend** has zero coupling; if the migration fails, the frontend still renders and shows whatever errors come back from the SSE error frame.
- **Database / Alembic** is unaffected. No migration is added.
- **Telegram bot** has no AI usage today and is not coupled to this work.
- **CI / tests** depend on the test mocks being updated; otherwise they fail at import-time.

### Potential Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Groq's free-tier rate limits are tight enough to interrupt a real chat session. | Medium | Error frame surfaces the SDK's "try again in Xs" message verbatim. User can wait and retry. If it becomes a recurring annoyance, evaluate Groq's paid tier or another vendor in a future spec. |
| Llama 3.3 70B output quality is meaningfully worse than Claude on CV/cover-letter prompts. | Medium | Functional spec explicitly accepts quality differences. If unacceptable in practice, a future spec can add a higher-quality model option (e.g., a paid Groq tier or a different vendor). |
| Streaming chunk shape from Groq SDK differs subtly from Anthropic's (e.g., `delta.content` is `None` on the first chunk and on `finish_reason` chunks). | High | Filter `None` deltas in the stream loop. Verify behavior manually after first wire-up — this is the only spot likely to need a small adjustment. |
| Lingering imports of `anthropic` somewhere we missed (e.g., in a utility, conftest, or doc-string). | Low | Grep for `anthropic`/`claude_client`/`stream_claude_response` after the rewrite. Both terms must return zero hits in `app/` and `tests/` (unrelated string matches in `context/spec/004*` are expected and fine — those are historical specs). |
| Architecture doc and `.env.example` drift, leaving stale Anthropic instructions for future contributors. | Low | Update both as part of the same change set; reviewer checks. |
| Past chat messages displayed to the user contain Anthropic-flavored phrasing ("Claude here..." or similar) that becomes incongruous after the swap. | Low | Functional spec accepts this — no rewrite of historical messages. |

---

## 4. Testing Strategy

### Unit / Integration (automated)

- **Existing pytest suite (`backend/tests/test_chat.py`)** must pass unmodified in behavior. Only mock target names change (`stream_claude_response` → `stream_llm_response`). Run via `pytest backend/tests/test_chat.py`.
- **Settings tests:** if any exist, ensure `GROQ_API_KEY` and `GROQ_MODEL` defaults round-trip correctly. Add a single small test for the default model value (`"llama-3.3-70b-versatile"`).
- **No integration tests against the real Groq API** — keep the test suite hermetic; rely on mocked streams as today.

### Manual Verification (post-deploy in dev)

- With a valid `GROQ_API_KEY` in `.env` and `docker compose restart backend`:
  - Open `/applications/:id/chat` for an application with a linked CV. Send "Refine my CV". Confirm tokens stream in and a coherent response is produced.
  - Send "Write a cover letter" on an application without a linked CV. Confirm graceful behavior.
  - Send "Prep for interview". Confirm response.
  - Free-form follow-up message. Confirm history persists across page reload.
  - Clear history. Confirm DB row deletion and empty state.
- With `GROQ_API_KEY` invalid: send a chat message, confirm error frame surfaces a clear message and the input is re-enabled.
- With `GROQ_API_KEY` missing: confirm backend fails fast at startup with a clear error rather than booting and erroring on first chat request.

### Regression Surface

- Frontend SSE consumer must not need changes. If it does, the migration broke the protocol contract — investigate before merging.
- Authentication, application CRUD, CV CRUD, dashboard, metrics are unaffected and need no targeted regression. A quick smoke pass through the dashboard is sufficient.
