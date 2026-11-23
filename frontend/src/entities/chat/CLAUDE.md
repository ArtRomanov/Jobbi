# Chat Entity

Domain entity for AI chat messages scoped to a job application. Provides the ChatMessage type (re-exported from generated schema) and API functions: getChatHistory, clearChatHistory, and sendChatMessage (SSE streaming via raw fetch).

- `ChatRouteState` / `getChatDraft(location.state)`: the `{draft}` router-state contract for opening the chat with an unsent, pre-filled message.
- Change cards (spec 011 slice 7): `ChangeCard` = generated `ChangeCardRead` (`decided_at` is null while pending or stale). `ChatMessageRead.cards` is always present (`[]` for user messages and replies without edits), so locally built messages must pass `cards: []`. `acceptChangeCard` / `rejectChangeCard` call `POST …/chat/cards/{id}/accept|reject`.
- `sendChatMessage(appId, content, { onToken, onCards, onDone, onError })`: frame payloads are JSON — `token` `{"text"}`, `error` `{"detail"}` (decoded by `readField`), `cards` a `ChangeCard[]` sent before `done` on every reply (often `[]`), parsed by `parseCardsEvent`, which drops malformed entries instead of failing the stream.
