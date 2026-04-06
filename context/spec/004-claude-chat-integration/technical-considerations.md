<!--
This document describes HOW to build the feature at an architectural level.
It is NOT a copy-paste implementation guide.
-->

# Technical Specification: Claude Chat Integration

- **Functional Specification:** `context/spec/004-claude-chat-integration/functional-spec.md`
- **Status:** Draft
- **Author(s):** Poe (AI Technical Architect)

---

## 1. High-Level Technical Approach

This feature adds an AI chat assistant powered by Claude, scoped to individual job applications. It requires a new `chat_messages` table for persisted history, a streaming chat endpoint using Server-Sent Events (SSE), integration with the Anthropic Python SDK, and a frontend chat page with real-time message rendering.

The backend builds a system prompt from the application context (company, role, job URL, notes) and linked CV data, sends the conversation to Claude via the Anthropic API, and streams the response back to the frontend via SSE. Messages are persisted in the database for history.

**Model:** Claude Sonnet (`claude-sonnet-4-6-20250514`) — fast, cost-effective, good quality for job search tasks.

**Systems affected:** New chat model + migration, new streaming endpoint, Anthropic SDK dependency, new frontend chat page, modification to application panel (add AI Assistant button).

---

## 2. Proposed Solution & Implementation Plan

### 2.1 Data Model / Database Changes

**Table: `chat_messages`**

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID (String 36) | PK | Generated server-side |
| `application_id` | UUID (String 36) | FK → applications.id, NOT NULL, indexed | CASCADE delete |
| `role` | VARCHAR(20) | NOT NULL | "user" or "assistant" |
| `content` | TEXT | NOT NULL | Message text |
| `created_at` | DATETIME | NOT NULL | server_default |

**Migration:** Single Alembic migration creates the table.

### 2.2 API Contracts

**Chat endpoints** (all require JWT):

**`GET /api/v1/applications/{id}/chat`** — Get chat history for an application
- Success (200): `ChatMessageRead[]` (ordered by created_at asc)

**`POST /api/v1/applications/{id}/chat`** — Send a message and get a streaming response
- Request: `{ content: string }` (the user's message)
- Response: `text/event-stream` (SSE)
- SSE events:
  - `event: token` / `data: {"text": "..."}` — each chunk of Claude's response
  - `event: done` / `data: {"message_id": "..."}` — signals completion, includes the saved assistant message ID
  - `event: error` / `data: {"detail": "..."}` — error during generation
- Side effects: saves user message to DB before streaming, saves complete assistant message after streaming

**`DELETE /api/v1/applications/{id}/chat`** — Clear chat history for an application
- Success (200): `{ message: "Chat history cleared." }`

### 2.3 Backend Components

| Path | Responsibility |
|---|---|
| `backend/app/models/chat_message.py` | SQLAlchemy `ChatMessage` model |
| `backend/app/schemas/chat.py` | Pydantic schemas: `ChatMessageCreate`, `ChatMessageRead`, `ChatRequest` |
| `backend/app/services/chat_service.py` | Chat logic: get history, save message, build system prompt, call Claude API with streaming |
| `backend/app/services/claude_client.py` | Anthropic SDK wrapper: initialize client, stream message, handle errors |
| `backend/app/api/v1/chat.py` | Route handlers: GET history, POST stream, DELETE clear |

### 2.4 System Prompt Construction

The system prompt is built dynamically per request from application + CV data:

```
You are a helpful career assistant for a job seeker. You have access to the following context about a specific job application:

**Application:**
- Company: {company_name}
- Role: {role_title}
- Job URL: {job_url}
- Status: {status}
- Notes: {notes}

**Candidate's CV ({cv_name}):**
- Summary: {summary}
- Work Experience: {formatted_experience}
- Education: {formatted_education}
- Skills: {skills}
- Languages: {languages}

Provide specific, actionable advice tailored to this role and company. Be concise and professional.
```

If no CV is linked, the CV section is omitted.

### 2.5 Streaming Architecture

```
Frontend                    Backend                         Anthropic API
   |                           |                                |
   |-- POST /chat ------------>|                                |
   |                           |-- save user message to DB      |
   |                           |-- build system prompt           |
   |                           |-- anthropic.messages.stream() ->|
   |                           |                                |
   |<-- SSE: token {"text"} ---|<-- stream chunk ---------------|
   |<-- SSE: token {"text"} ---|<-- stream chunk ---------------|
   |<-- SSE: token {"text"} ---|<-- stream chunk ---------------|
   |                           |                                |
   |                           |<-- stream complete ------------|
   |                           |-- save assistant message to DB  |
   |<-- SSE: done -------------|                                |
```

FastAPI's `StreamingResponse` with `media_type="text/event-stream"` handles the SSE transport. The Anthropic SDK's `client.messages.stream()` context manager provides an async iterator of text chunks.

### 2.6 Frontend Components (FSD)

| Layer/Slice | Path | Content |
|---|---|---|
| `entities/chat` | `frontend/src/entities/chat/` | ChatMessage type (from OpenAPI), API calls: getHistory, sendMessage (returns EventSource/fetch stream), clearHistory |
| `features/chat-interface` | `frontend/src/features/chat-interface/` | ChatWindow component (message list + input), MessageBubble component, QuickActionBar component, streaming message handler |
| `pages/chat` | `frontend/src/pages/chat/` | Chat page scoped to application (route: /applications/:id/chat) |

Modified:
| Layer/Slice | Change |
|---|---|
| `features/application-panel` | Add "AI Assistant" button linking to /applications/{id}/chat |
| `app/router` | Add `/applications/:id/chat` route (protected) |

### 2.7 Frontend Streaming

The frontend uses `fetch()` with the streaming response body:

```typescript
const response = await fetch(url, { method: "POST", headers, body });
const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  const text = decoder.decode(value);
  // Parse SSE events and update UI
}
```

Messages are rendered progressively — the assistant message grows as tokens arrive.

### 2.8 Quick-Action Prompt Templates

Stored as constants in `features/chat-interface/lib/constants.ts`:

- **Refine CV:** "Please review my CV and suggest specific improvements for the {role_title} role at {company_name}. Focus on wording, structure, and keyword optimization."
- **Cover Letter:** "Please write a tailored cover letter for the {role_title} position at {company_name}, based on my CV and the job description."
- **Interview Prep:** "Please help me prepare for an interview for the {role_title} role at {company_name}. Suggest likely interview questions, key topics to research about the company, and preparation tips."

### 2.9 Dependencies

**Backend:**
- `anthropic` — Official Anthropic Python SDK (add to pyproject.toml)

**Frontend:**
- No new dependencies (uses native fetch for SSE)

### 2.10 Configuration

| Env Variable | Purpose | Example |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude | `sk-ant-api03-...` |

Add to `.env.example` and `core/config.py` Settings.

---

## 3. Impact and Risk Analysis

**System Dependencies:**
- Requires a valid Anthropic API key (external service dependency)
- Depends on application and CV data from previous features

**Potential Risks & Mitigations:**

| Risk | Impact | Mitigation |
|---|---|---|
| API key missing or invalid | Chat feature non-functional | Graceful error: "AI Assistant is not configured. Please add your Anthropic API key." |
| Anthropic API rate limits | Throttled responses | Single-user app unlikely to hit limits. Show error toast if rate limited. |
| Long responses blocking | Slow UX | Streaming solves this — user sees tokens immediately |
| API costs | Unexpected bills | Sonnet is cost-effective. Out of scope: no cost tracking in V1. |
| Large CV/context exceeds token limit | API error | Truncate context if needed. Sonnet supports 200K tokens — unlikely to be hit. |

---

## 4. Testing Strategy

**Backend (pytest):**
- Chat message CRUD: save, retrieve history, clear
- System prompt construction (with and without CV)
- Streaming endpoint (mock Anthropic client, verify SSE format)
- Authorization: can't access another user's application chat

**Frontend (Vitest + Testing Library):**
- Chat page rendering with message history
- Message input and send behavior
- Quick-action button rendering and disabled states
- Streaming message progressive rendering (mock SSE)
