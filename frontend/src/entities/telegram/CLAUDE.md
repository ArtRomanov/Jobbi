# Telegram Entity

Domain entity for the user's Telegram bot link. Exposes generated-schema types (`TelegramStatus`, `ConnectionCode`) and API calls: `getTelegramStatus`, `generateConnectionCode`, `disconnectTelegram`.

Note: the backend serializes `expires_at` / `linked_at` as naive UTC (no `Z`). Parse them as UTC, not with a bare `new Date()`.
