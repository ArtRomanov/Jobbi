# Chat Entity

Domain entity for AI chat messages scoped to a job application. Provides the ChatMessage type (re-exported from generated schema) and API functions: getChatHistory, clearChatHistory, and sendChatMessage (SSE streaming via raw fetch).

- `ChatRouteState` / `getChatDraft(location.state)`: the `{draft}` router-state contract for opening the chat with an unsent, pre-filled message.
- Change cards (spec 011 slice 7): `ChangeCard` (incl. `message_id`; `decided_at` is null while pending or stale) and the `cards` field on `ChatMessage` are **temporary local types** in `model/types.ts`, written against the agreed contract; swap them for `components["schemas"]["ChangeCardRead"]` after the schema is regenerated. `acceptChangeCard` / `rejectChangeCard` call `POST …/chat/cards/{id}/accept|reject`.
- `sendChatMessage(appId, content, { onToken, onCards, onDone, onError })`: the SSE `cards` event (JSON `ChangeCard[]`, after the text, before `done`) is parsed by `parseCardsEvent`, which drops malformed entries instead of failing the stream.
