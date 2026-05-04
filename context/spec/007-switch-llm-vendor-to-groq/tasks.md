# Tasks: Switch LLM Vendor from Anthropic to Groq

- **Functional Spec:** [`functional-spec.md`](./functional-spec.md)
- **Technical Considerations:** [`technical-considerations.md`](./technical-considerations.md)

---

## Slice 1: Chat works end-to-end on Groq with default model

After this slice, opening any application's chat page and sending a message produces a streamed response from `llama-3.3-70b-versatile` via Groq. No Anthropic code or config remains. Existing chat history continues to render.

- [x] **Slice 1: Migrate the LLM client to Groq**
  - [x] Swap the SDK in `backend/pyproject.toml`: remove `anthropic>=0.40,<1`, add `groq>=0.13,<1`. Refresh dependencies in the backend image. **[Agent: python-backend]**
  - [x] Update `backend/app/core/config.py`: remove `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL`; add `GROQ_API_KEY: str` and `GROQ_MODEL: str = "llama-3.3-70b-versatile"`. Add a `model_validator(mode="after")` that fails fast with a clear error when `GROQ_API_KEY` is empty. **[Agent: python-backend]**
  - [x] Update `.env` and `.env.example`: remove the two `ANTHROPIC_*` lines; add `GROQ_API_KEY=` and `GROQ_MODEL=llama-3.3-70b-versatile`. **[Agent: python-backend]**
  - [x] Create `backend/app/services/groq_client.py` exposing `build_system_prompt(application, cv)` (port unchanged from `claude_client.py`) and `async def stream_llm_response(system_prompt, messages) -> AsyncIterator[str]` that calls `groq.AsyncGroq().chat.completions.create(model=settings.GROQ_MODEL, messages=[{"role":"system","content":system_prompt}, *messages], stream=True, max_tokens=4096)` and yields `chunk.choices[0].delta.content` filtering `None` deltas. Surface `groq.APIError` and subclasses as raised exceptions for the SSE error frame to catch. **[Agent: python-backend]**
  - [x] Delete `backend/app/services/claude_client.py`. **[Agent: python-backend]**
  - [x] Update `backend/app/services/chat_service.py`: change the import to `from app.services.groq_client import build_system_prompt, stream_llm_response` and the call to `stream_llm_response(...)`. Verify no other call sites exist. **[Agent: python-backend]**
  - [x] Update `backend/tests/test_chat.py`: change the import path to `app.services.groq_client` and the two `monkeypatch.setattr` strings from `app.services.chat_service.stream_claude_response` to `app.services.chat_service.stream_llm_response`. **[Agent: python-backend]**
  - [x] Update `context/product/architecture.md` §4 "External Services & APIs": replace the `Anthropic API ...` line with `Groq API (direct HTTPS calls via official Python SDK)`. **[Agent: python-backend]**
  - [x] Grep for residual `anthropic`, `claude_client`, and `stream_claude_response` references in `backend/app/` and `backend/tests/`. Expect zero hits. References under `context/spec/004-claude-chat-integration/` and `context/spec/006-telegram-bot-integration/` are historical and may remain. **[Agent: python-backend]**
  - [x] Rebuild and restart: `docker compose up -d --build backend`. Confirm the backend container is healthy and `/api/v1/health` returns 200. **[Agent: python-backend]**
  - [x] Run the backend test suite: `docker exec awos-backend-1 pytest tests/test_chat.py -v`. Expect all chat tests to pass. **[Agent: python-backend]**
  - [x] **Verify (golden path):** With a valid `GROQ_API_KEY` set, log in to the frontend, open an application's side panel, click "AI Assistant", send "Tell me about this role." Confirm tokens stream in word-by-word, the assistant reply renders normally, and refreshing the page restores the conversation. **[Agent: qa-tester]**
  - [x] **Verify (quick actions):** On an application with a linked CV, click "Refine my CV" — confirm a useful streamed response. On any application, click "Write a cover letter" and "Prep for interview" — confirm both stream useful responses. **[Agent: qa-tester]**
  - [x] **Verify (history compatibility):** Open a conversation that contains pre-migration messages (produced by Anthropic). Confirm those messages render verbatim with no error. **[Agent: qa-tester]**
  - [x] **Verify (failure surfacing):** Set `GROQ_API_KEY=invalid` in `.env`, restart the backend, send a message. Confirm an inline error appears in the conversation area, the user's message remains visible, and the input is re-enabled for retry. Restore the valid key when done. **[Agent: qa-tester]**
  - [x] **Verify (fail-fast on missing key):** Unset `GROQ_API_KEY` (or set to empty string), restart the backend. Confirm the container fails at startup with a clear error naming `GROQ_API_KEY` rather than booting and failing later. Restore the valid key. **[Agent: qa-tester]**

---

## Slice 2: Friendly error mapping (polish)

The tech spec marked this as a follow-up; SDK default messages are usable but noisy. This slice replaces them with concise, user-friendly text for the common cases.

- [x] **Slice 2: Map common Groq exceptions to friendly messages**
  - [x] In `backend/app/services/groq_client.py`, catch `groq.AuthenticationError`, `groq.RateLimitError`, and `groq.APIConnectionError` inside `stream_llm_response` and re-raise with the user-facing strings listed in technical-considerations §2.7. Other `groq.APIStatusError` subclasses fall through with their default message. **[Agent: python-backend]**
  - [x] **Verify (rate-limit message):** Trigger a rate limit (e.g., spam the chat endpoint quickly with curl, or temporarily set `GROQ_MODEL` to a free-tier-throttled value and exceed quota). Confirm the inline error reads "Rate limit reached. Please try again in a moment." rather than the raw SDK message. **[Agent: qa-tester]**
  - [x] **Verify (auth-error message):** Set `GROQ_API_KEY=invalid`, restart, send a message. Confirm the inline error reads "AI service authentication failed. Please contact the operator." Restore the valid key. **[Agent: qa-tester]**
