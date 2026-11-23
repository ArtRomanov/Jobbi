# Chat Page

Full-screen chat page for the AI assistant, scoped to a single application via route param `:id`. Composes chat entity APIs and chat-interface feature components. Handles SSE streaming, optimistic user messages, and clear-history confirmation.

- Optional router state `{draft}` (`ChatRouteState` from `entities/chat`, e.g. from "Add & tailor CV") pre-fills `ChatInput` but is never sent automatically. The page reads it once on mount, then replaces the history entry with `state: null` (same URL) so a reload or Back does not re-fill.
- Streaming: the backend always sends `event: cards` before `done` (often `[]`, ignored). A non-empty `cards` moves the reply into `messages` at once under its persisted id (`cards[0].message_id`), so the history reload after `done` keeps the same React keys and a card decision started in between is not reset. A text-only reply is appended as a temp message on `done` until the reload replaces it.
