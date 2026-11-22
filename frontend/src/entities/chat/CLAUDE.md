# Chat Entity

Domain entity for AI chat messages scoped to a job application. Provides the ChatMessage type (re-exported from generated schema) and API functions: getChatHistory, clearChatHistory, and sendChatMessage (SSE streaming via raw fetch).

- `ChatRouteState` / `getChatDraft(location.state)`: the `{draft}` router-state contract for opening the chat with an unsent, pre-filled message.
