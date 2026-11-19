import type { components } from "@/shared/api";

/** Link status returned by GET /api/v1/telegram/status */
export type TelegramStatus = components["schemas"]["TelegramStatus"];

/** One-time code returned by POST /api/v1/telegram/connection-code */
export type ConnectionCode = components["schemas"]["ConnectionCodeResponse"];
