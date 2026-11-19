import type { TelegramStatus } from "@/entities/telegram";
import type { TelegramConnectionState } from "../model/types";

const HAS_TZ_SUFFIX = /(Z|[+-]\d{2}:?\d{2})$/i;

/**
 * Parse an API timestamp as UTC. Accepts both Z/offset-suffixed values and
 * naive UTC datetimes (older backend builds), which `new Date()` would
 * otherwise treat as local time.
 */
export function parseUtcDate(value: string): Date {
  return new Date(HAS_TZ_SUFFIX.test(value) ? value : `${value}Z`);
}

/** Format an epoch-ms timestamp as a short local clock time, e.g. "14:32". */
export function formatClockTime(epochMs: number): string {
  return new Date(epochMs).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Short status line announced to screen readers (one aria-live region). */
export function getStatusLabel(state: TelegramConnectionState): string {
  switch (state.status) {
    case "loading":
      return "Checking Telegram status...";
    case "load-error":
      return "Could not load Telegram status.";
    case "not-connected":
      return state.isCodeExpired ? "Not connected (code expired)" : "Not connected";
    case "awaiting-link":
      return "Not connected yet — waiting for your code";
    case "connected":
      return state.username ? `Connected as @${state.username}` : "Connected";
  }
}

/** Map the API status payload onto the UI state machine. */
export function statusToState(status: TelegramStatus): TelegramConnectionState {
  return status.connected
    ? { status: "connected", username: status.telegram_username ?? null }
    : { status: "not-connected", isCodeExpired: false };
}
