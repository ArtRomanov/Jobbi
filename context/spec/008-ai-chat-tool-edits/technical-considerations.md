# Technical Specification: AI Chat Edits Application & CV via Tool Calls

- **Functional Specification:** [`functional-spec.md`](./functional-spec.md)
- **Status:** Draft
- **Author(s):** Architect (AI)

---

## 1. High-Level Technical Approach

The chat path today (`chat_service.stream_chat_response` → `groq_client.stream_llm_response`) hands the LLM a system prompt plus the prior message history and streams plain text back over SSE. We extend it in three coordinated steps:

1. **Tool definitions on the LLM call.** Pass a small, fixed set of mutation tools (5 total) to Groq via `client.chat.completions.create(..., tools=[...], tool_choice="auto")`. The model decides per turn whether to emit text only, tool calls only, or both. Llama 3.3 70B Versatile on Groq supports OpenAI-compatible tool-calling; this is documented and stable.
2. **Server-side staging instead of execution.** When the model emits a tool call, the backend does **not** run the mutation. It validates the call shape, persists a `chat_change_cards` row in `pending` state, and emits the card as an SSE `event: card` frame so the frontend can render it inline. The tool's "result" returned to the model is a stub like `{"status": "queued_for_user_review", "card_id": "..."}` — no echo of the proposed payload, so the model doesn't get confused into reasoning about whether the change "happened".
3. **Per-card resolution endpoint.** Two new endpoints, `POST /api/v1/chat-cards/{id}/accept` and `.../reject`, transition a card and (on accept) apply the staged mutation atomically through the existing application/CV services, under the requesting user's auth.

The frontend chat page renders cards as a new bubble type interleaved with text messages. The history endpoint returns cards alongside messages so a refreshed conversation reproduces the same layout, including pending cards that the user can still resolve.

The system prompt picks up a short instructions block teaching the model when to use tools vs. give text-only advice. The conversation passed to subsequent turns includes the resolved-card decisions as `tool` role messages, so the model has continuity ("the user accepted the summary rewrite, so my context now reflects the new summary"). For pending cards we omit the tool-result message until the user resolves, to avoid confusing the model with stale state.

Reference: Groq tool-calling docs at https://console.groq.com/docs/tool-use; OpenAI-compatible message shape at https://platform.openai.com/docs/api-reference/chat/create.

---

## 2. Proposed Solution & Implementation Plan (The "How")

### 2.1 Architecture Changes

No new services or infrastructure. The chat path remains a single FastAPI endpoint backed by SQLite. The change is internal: the `groq_client` learns about tools, `chat_service` orchestrates card creation, two new endpoints handle resolution, and a new table holds card state.

The "AI Integration" line in `context/product/architecture.md` does not need to change — it's still Groq via the official SDK.

### 2.2 Data Model / Database Changes

One new table.

| Table | Purpose |
|---|---|
| `chat_change_cards` | One row per AI-proposed change. Linked to the assistant `chat_message` that produced it and to the application it scopes. Holds the proposed mutation, before/after snapshot, and resolution state. |

Columns (descriptive — see Alembic migration for exact types):

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | Card identifier; surfaced in SSE frame and used by the resolution endpoints. |
| `chat_message_id` | FK → `chat_messages.id` ON DELETE CASCADE | The assistant turn this card belongs to. |
| `application_id` | FK → `applications.id` ON DELETE CASCADE | Scope of the card; ownership check uses this. |
| `tool_name` | String | One of the five tool names (see §2.4). Enables dispatch on Accept. |
| `arguments` | JSON | The validated tool arguments from the LLM. |
| `target_kind` | String | `application` or `cv` — for human-readable rendering and audit. |
| `target_label` | String | Short rendering hint (e.g., "Application status", "CV: Work experience #2"). Computed at card-creation time so history renders correctly even if the structure later changes. |
| `before_value` | JSON nullable | Snapshot of the field/entry at card-creation time. Null for pure additions. |
| `after_value` | JSON | The proposed new value as the user will see it. |
| `state` | String | `pending` \| `accepted` \| `rejected` \| `stale`. |
| `error_message` | String nullable | Set when an Accept attempt failed; surfaced inline. Cleared on successful Accept or Reject. |
| `created_at` | datetime | Server default. |
| `resolved_at` | datetime nullable | When state moved off `pending`. |

No changes to `chat_messages`, `applications`, or `cvs`. The existing `application.cv_id` is consulted at card-creation time to resolve which CV the assistant may touch.

A standard Alembic migration creates the table with the FKs and an index on `(application_id, state)` to make the history query fast.

### 2.3 Tool Catalog

Five tools are exposed to the model. The names are short and non-overlapping to keep the model's tool-selection accuracy high. Argument schemas are JSON Schema, strict (`additionalProperties: false`), and validated with Pydantic before persistence.

| Tool name | Purpose | Arguments (sketch) |
|---|---|---|
| `update_application_field` | Edit a single application field. | `{ field: "status" \| "notes" \| "role_title" \| "company_name" \| "job_url", value: string }`. `status` value is constrained to the `ApplicationStatus` enum. |
| `update_cv_field` | Edit a single scalar/text CV field. | `{ field: "summary" \| "skills" \| "languages", value: string }` and a separate variant for `personal_info` keyed sub-fields. |
| `add_cv_list_entry` | Append an entry to `work_experience` or `education`. | `{ list_name: "work_experience" \| "education", entry: <typed object> }` — the entry shape mirrors what the existing CV form/editor stores. |
| `update_cv_list_entry` | Replace an entry at a given index. | `{ list_name, index: int, entry }`. |
| `remove_cv_list_entry` | Remove an entry at a given index. | `{ list_name, index: int }`. |

Why this granularity rather than 12 narrow tools or 2 broad ones: The chat model picks correctly among a small, distinctly-named set; 12 tools degrades selection accuracy in our experience, and 2 broad tools (e.g., `update_application(fields)`) push too much logic into argument shape, which the model handles less reliably than tool-name discrimination. Five is the sweet spot.

The tool definitions live in a single module: `backend/app/services/chat_tools.py`. It exports the JSON-schema list passed to Groq and a dispatcher that maps `tool_name` + `arguments` to the right service-layer mutation.

### 2.4 Streaming Endpoint Changes

**Existing endpoint:** `POST /api/v1/applications/{application_id}/chat`. SSE protocol stays. New frame type added:

```
event: card
data: {"id": "<uuid>", "tool_name": "update_cv_field", "target_kind": "cv",
       "target_label": "CV summary", "before_value": "<text>",
       "after_value": "<text>", "state": "pending"}
```

Token frames continue to interleave with card frames in the order the model produces them. `event: done` and `event: error` are unchanged. The frontend's existing SSE parser already dispatches by `event:` name, so the addition is additive.

**Pseudocode** (in `chat_service.stream_chat_response`):

```
for event in groq_stream:
    if event is text_delta:
        yield text frame
    elif event is tool_call_delta:
        accumulate tool_call args
    elif event is tool_call_complete:
        validate args; create chat_change_card row (pending);
        push tool result {"card_id": <id>, "status": "queued"} into the
        next iteration's tool messages; yield card frame
    elif event is finish:
        save assistant chat_message with the accumulated text; commit
```

Groq's stream surfaces tool calls as deltas with a stable index — accumulation is mechanical. We only persist a card once its arguments are complete and have passed Pydantic validation.

### 2.5 Resolution Endpoints

| Method & path | Body | Behavior |
|---|---|---|
| `POST /api/v1/chat-cards/{id}/accept` | none | 1) Load card. 2) Verify the requesting user owns the linked application. 3) Verify the card is `pending`. 4) Verify the target entity still exists and the proposed change still applies (e.g., index is in range). 5) In a single DB transaction, apply the mutation through the existing `application_service` / `cv_service` and flip the card to `accepted` with `resolved_at`. 6) On any precondition failure, set `state="stale"` and return the failure detail; on transient failure, leave `pending` and write `error_message`. |
| `POST /api/v1/chat-cards/{id}/reject` | none | Verify ownership and `pending` state, flip card to `rejected` with `resolved_at`. No mutation runs. |

Both return the updated card representation. They do **not** stream — they're plain JSON endpoints.

A small new module: `backend/app/services/chat_card_service.py` houses the resolution logic and the mutation dispatcher (which invokes per-tool functions in `chat_tools.py`).

### 2.6 History Endpoint Changes

`GET /api/v1/applications/{id}/chat` today returns a list of `ChatMessage`. We extend the response so each assistant message that produced cards includes them:

```
[
  {"id": "...", "role": "user", "content": "...", "created_at": "..."},
  {"id": "...", "role": "assistant", "content": "...", "created_at": "...",
   "cards": [<card>, <card>]},
  ...
]
```

Cards in `pending` state are still resolvable from the history view — the frontend renders them with active Accept/Reject buttons.

### 2.7 LLM Context: Conversation Continuity

When building the `messages` payload for a new turn, history mapping changes as follows:

- `user` and `assistant` messages map as today.
- For each `accepted` card on a prior assistant message, append a `tool` role message with the card id, the original tool call, and a result like `{"applied": true}`. This signals to the model that the change took effect, and the system prompt's snapshot of application/CV (rebuilt fresh each turn from DB state) confirms the new content.
- For `rejected` cards, append a tool result `{"applied": false, "rejected_by_user": true}`.
- For `pending` cards, omit the tool result. Per Groq docs, an unanswered tool call in history can confuse the model; we include the assistant's tool_call but with no matching tool result, OR strip the tool_call from history. The cleaner of the two: strip pending tool_calls from the history we send back. Decision: strip pending tool_calls when reconstructing history; the model can still re-propose if the user asks again.
- For `stale` cards, treat as `rejected` for context purposes.

This logic lives in `chat_service.build_chat_messages_for_llm` (a new helper) and is unit-tested.

### 2.8 System Prompt Updates

`build_system_prompt` gains a short tools instruction block:

> "You can edit the user's application and linked CV using the provided tools. Use a tool when the user asks for a concrete change (e.g., 'rewrite my summary', 'mark this as Applied'). For each change, call the appropriate tool with the specific new value; do not narrate what you would do without calling the tool. The user will see your proposed changes as cards in the chat and approve or reject each one. If the user is asking for advice, brainstorming, or open-ended discussion, just reply with text. Never call a tool that edits something the user did not ask to change."

The application/CV context section is unchanged.

### 2.9 Frontend Component Breakdown

| Path | Purpose |
|---|---|
| `frontend/src/entities/chat/api/accept-card.ts` | `POST /chat-cards/:id/accept`, returns updated card. |
| `frontend/src/entities/chat/api/reject-card.ts` | `POST /chat-cards/:id/reject`, returns updated card. |
| `frontend/src/entities/chat/model/types.ts` | Add `ChatChangeCard` type and extend `ChatMessage` to optionally include `cards: ChatChangeCard[]`. |
| `frontend/src/entities/chat/api/send-message.ts` | Extend SSE parser with a `case "card":` branch that calls a new `onCard(card)` callback. |
| `frontend/src/features/chat-interface/ui/change-card.tsx` | New component. Renders target label, before/after side-by-side blocks (no diff library — plain `<pre>` blocks side by side or stacked, with red/green left-border indicators). Accept/Reject buttons. Loading + error sub-states. |
| `frontend/src/features/chat-interface/ui/chat-window.tsx` | Render cards inline between message bubbles in chronological order. |
| `frontend/src/pages/chat/ui/chat-page.tsx` | Wire `onCard` to push the new card into local state; wire Accept/Reject handlers to the API and update card state in place; on Accept success, optionally trigger the application/CV detail invalidation in TanStack Query so other panels reflect the change. |

No FSD layer additions — `chat-card` types and APIs live in the existing `entities/chat`.

A simple side-by-side block layout is used instead of a real diff library (e.g., `diff`, `react-diff-viewer`). Reasons: zero new dependency, the block sizes we typically render (one bullet, a summary, a status string) make a real diff overkill, and we keep bundle size small. If a richer diff is desired later it's a localized swap.

### 2.10 Deletion Behavior

- If the linked application is deleted, `chat_change_cards` cascade-delete with the chat messages (already cascading via `application_id` FK on `chat_messages` and the new FK on `chat_change_cards`).
- If the linked CV is removed (set to null on the application or deleted from the user), no cascade is needed — pending CV cards become Stale on next Accept attempt because the lookup fails. We do not pre-mark them Stale to avoid scanning all pending cards on every CV change.

---

## 3. Impact and Risk Analysis

### System Dependencies

- **Groq tool-calling reliability with `qwen/qwen3.8-27b` (preview; replaced Llama 3.3 70B, unavailable on the account since 2026-11-22).** A live tool call returned a correct `tool_calls` on 2026-11-22, but model behavior on edge cases (e.g., the user asks for ten changes at once, or asks something ambiguous) needs prompt iteration. The system prompt in §2.8 is the main lever.
- **Existing services.** `application_service.update_application` and `cv_service.update_cv` (or per-field updaters) must accept partial updates. Verify; add a thin per-field helper if missing.
- **Frontend SSE consumer.** Already extensible — adding a `card` event branch is additive.
- **TanStack Query invalidation.** On Accept, the `applications/:id` query and any `cvs/:id` query should refetch so other panels are consistent. Standard pattern; not a risk.

### Potential Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Model hallucinates tool arguments (invalid status value, out-of-range index, wrong field name). | Medium | Strict JSON Schema on tool definitions + Pydantic validation server-side. Invalid calls produce a friendly inline error message in the chat (per FS §2.5) and **no card is created**. The model sees the validation failure as a tool result and can retry. |
| Model proposes changes the user did not request (overreach). | Medium | System prompt explicitly forbids editing things the user did not ask to change. User sees every proposed change as a card and can Reject. No silent edits regardless of model behavior. |
| User accepts a card whose underlying entity was modified elsewhere between proposal and acceptance (lost-update). | Low–Medium | Accept handler re-reads the current state and applies the diff verbatim — last writer wins. We do not enforce optimistic concurrency for V1; the audit trail is the safety net. Could be revisited if it bites in practice. |
| Pending cards accumulate forever (user never decides). | Low | They remain resolvable indefinitely. If a card's target is gone or the field shape has changed, Accept transitions it to Stale. We could add a TTL later if storage growth becomes an issue. |
| Model emits tool calls when the user wanted text-only advice (over-eagerness). | Medium | Prompt tuning is the primary tool. Quick-action templates already steer the model; we tune those templates if needed. As a backstop, the user simply rejects unwanted cards. |
| Bundle size bloat from a diff library. | Low | We deliberately do not pull one in; plain side-by-side blocks suffice for the field sizes we render. |
| SQLite JSON updates on `cvs.work_experience` / `cvs.education` are full-row rewrites. | Low | This is already how CV updates work today — not new. List operations remain O(rows-of-cv-text), which is small. |
| `tool_choice="auto"` plus a high-temperature reply produces repeat tool calls (model proposes the same change twice). | Low | Idempotency: dedupe at card-creation time by `(chat_message_id, tool_name, arguments)`. If a duplicate is detected, drop it silently. |

---

## 4. Testing Strategy

### Unit (automated)

- **Tool argument validation.** Parametrized tests over each tool: valid args produce a card; invalid args produce a `ToolValidationError` mapped to an inline error message. Cover enum-value boundaries on `update_application_field` (status), index-out-of-range on list operations, missing required entry sub-fields.
- **Card resolution.** Accept happy path mutates the target and flips state. Accept on missing target sets Stale. Reject flips state without mutating. Cross-user Accept returns 404. Re-Accept on settled card returns 409.
- **History reconstruction for the LLM.** Given a chat with a mix of pending/accepted/rejected/stale cards, the helper produces the expected `messages` array (pending tool_calls stripped, accepted/rejected emit tool results, system prompt rebuilt from current DB state).
- **Streaming pipeline.** Mock the Groq client to emit a deterministic sequence of text deltas + tool calls; assert the SSE frames produced by `stream_chat_response` are correct (`event: token`, `event: card`, `event: done`).
- **Idempotency.** Two identical tool calls in one turn produce one card.

### Integration (automated)

- **End-to-end Accept flow.** With Groq mocked, send a chat message that triggers a tool call, parse the `event: card` frame, POST `/accept`, GET the application — confirm the field is updated. Same for CV summary, list-add, list-update, list-remove.
- **History endpoint** returns messages with their cards; pending cards survive a refresh.

### Manual (post-deploy)

- Real Groq calls: ask for a summary rewrite, an interview status flip, three bullet refinements, an addition of a new work experience entry. Inspect that cards render, decisions persist, and follow-up turns honor the new state.
- Reject path: propose, reject, confirm no DB write, confirm next turn doesn't re-propose unless asked.
- Stale path: propose a CV summary change, manually delete the CV in another tab, click Accept — confirm Stale state and clear error message.
- Failure path: invalid `GROQ_API_KEY` (auth error) — confirm the error frame still surfaces correctly and no card is created.

### Out of Scope for Tests

- Quality of model output (text rationale and proposed values). The user is the arbiter via Accept/Reject; we do not assert on model-generated content.
