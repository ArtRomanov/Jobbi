# Tasks: Claude Chat Integration

---

- [x] **Slice 1: Chat backend with streaming**
  - [x] Add `anthropic` to pyproject.toml. Add `ANTHROPIC_API_KEY` to config.py Settings and .env.example. Create `ChatMessage` SQLAlchemy model and Alembic migration. **[Agent: python-backend]**
  - [x] Create `claude_client.py`: Anthropic SDK wrapper — initialize client, build system prompt from application + CV context, stream message response. **[Agent: python-backend]**
  - [x] Create `chat_service.py`: get chat history, save user/assistant messages, build context from application + CV, orchestrate Claude streaming. **[Agent: python-backend]**
  - [x] Create chat schemas: `ChatRequest`, `ChatMessageRead`. Create chat routes: `GET /applications/{id}/chat` (history), `POST /applications/{id}/chat` (SSE stream), `DELETE /applications/{id}/chat` (clear). Mount in v1 router. **[Agent: python-backend]**
  - [x] Verify: curl GET history (empty), POST message with SSE streaming (mock or real API key), GET history (messages persisted), DELETE (cleared). **[Agent: qa-tester]**

---

- [x] **Slice 2: Chat page with streaming**
  - [x] Regenerate OpenAPI types. Create `entities/chat/` slice: ChatMessage type, API calls (getHistory, clearHistory), SSE streaming helper for sendMessage. **[Agent: typescript-frontend]**
  - [x] Create `features/chat-interface/` slice: `ChatWindow` (message list with auto-scroll), `MessageBubble` (user right / assistant left with timestamps), chat input (Enter to send, Shift+Enter for newline), streaming message handler that progressively renders assistant response. **[Agent: typescript-frontend]**
  - [x] Create `pages/chat/` page: scoped to application via route param. Shows application context header (company, role, CV name). Loads chat history on mount. Sends messages via POST with SSE consumption. **[Agent: typescript-frontend]**
  - [x] Add `/applications/:id/chat` route (protected) to router. **[Agent: typescript-frontend]**
  - [x] Code review: Review SSE consumption, streaming state management, auto-scroll behavior, and FSD compliance. **[Agent: react-code-reviewer]**
  - [x] Verify: Navigate to chat page → see empty chat. Type message → response streams in word by word. Refresh → history preserved. **[Agent: qa-tester]**

---

- [x] **Slice 3: Quick actions and panel integration**
  - [x] Create quick-action prompt templates in `features/chat-interface/lib/constants.ts`. Add `QuickActionBar` component with 3 buttons: "Refine my CV" (disabled if no CV linked), "Write a cover letter", "Prep for interview". Each sends a pre-built prompt. **[Agent: typescript-frontend]**
  - [x] Add "AI Assistant" button to `features/application-panel/` that navigates to `/applications/{id}/chat`. **[Agent: typescript-frontend]**
  - [x] Wire quick actions into the chat page: buttons above the input, clicking sends the templated prompt as a user message. **[Agent: typescript-frontend]**
  - [x] Code review: Review prompt templates, disabled states, and navigation flow. **[Agent: react-code-reviewer]**
  - [x] Verify: Open application panel → click AI Assistant → chat page opens with context. Click "Refine my CV" → prompt sent → Claude responds. "Refine my CV" disabled when no CV linked. **[Agent: qa-tester]**

---

- [x] **Slice 4: Backend test suite for chat**
  - [x] Integration tests: save and retrieve chat history, clear history, message ordering. **[Agent: python-backend]**
  - [x] System prompt construction tests: with CV, without CV, with notes, with job URL. **[Agent: python-backend]**
  - [x] Streaming endpoint test: mock Anthropic client, verify SSE event format (token events + done event). **[Agent: python-backend]**
  - [x] Authorization tests: can't access another user's application chat. **[Agent: python-backend]**
  - [x] Verify: `pytest` runs all tests — 100% pass rate. **[Agent: qa-tester]**

---

- [x] **Slice 5: Frontend test suite for chat**
  - [x] Add MSW handlers for chat endpoints (GET history, POST stream mock, DELETE clear). **[Agent: typescript-frontend]**
  - [x] Chat page tests: renders message history, shows application context header. **[Agent: typescript-frontend]**
  - [x] Quick-action tests: buttons render, disabled state when no CV, click sends prompt. **[Agent: typescript-frontend]**
  - [x] Code review: Review test patterns for streaming mocks. **[Agent: react-code-reviewer]**
  - [x] Verify: `pnpm test` runs all tests — 100% pass rate. **[Agent: qa-tester]**
