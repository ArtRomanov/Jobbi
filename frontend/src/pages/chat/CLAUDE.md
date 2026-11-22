# Chat Page

Full-screen chat page for the AI assistant, scoped to a single application via route param `:id`. Composes chat entity APIs and chat-interface feature components. Handles SSE streaming, optimistic user messages, and clear-history confirmation.

- Optional router state `{draft}` (`ChatRouteState` from `entities/chat`, e.g. from "Add & tailor CV") pre-fills `ChatInput` but is never sent automatically. The page reads it once on mount, then replaces the history entry with `state: null` (same URL) so a reload or Back does not re-fill.
