import { colors } from "@/shared/ui";

/** How often to re-check link status while a connection code is on screen. */
export const STATUS_POLL_INTERVAL_MS = 3000;

/**
 * How the bot is referred to in instructions. The API does not expose the
 * bot's @username, so we use neutral wording instead of hardcoding a handle.
 */
export const BOT_DISPLAY_NAME = "the Jobbi bot";

/**
 * Server-side code lifetime. The client times expiry as this duration from
 * when the code arrived — never from `expires_at` — so client clock skew
 * (fast or slow) cannot shorten or stretch the window.
 */
export const CODE_TTL_MS = 10 * 60 * 1000;

/**
 * Extra wait after the TTL before the single final status check, so a link
 * the server committed at the last moment is still seen.
 */
export const EXPIRY_GRACE_MS = 3000;

export const MUTED_TEXT_STYLE = { fontSize: "0.875rem", color: colors.textMuted } as const;
