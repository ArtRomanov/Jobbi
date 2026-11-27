import type { ChangeCard } from "../model/types";

const OPS: ReadonlySet<unknown> = new Set([
  "replace",
  "insert",
  "remove",
  "replace_all",
]);
const STATES: ReadonlySet<unknown> = new Set([
  "pending",
  "accepted",
  "rejected",
  "stale",
]);
const POSITIONS: ReadonlySet<unknown> = new Set([
  "start",
  "end",
  "after_line",
  null,
]);

function isNullableString(value: unknown): boolean {
  return value === null || typeof value === "string";
}

/** Runtime check for a card parsed from the SSE `cards` event. */
export function isChangeCard(value: unknown): value is ChangeCard {
  if (typeof value !== "object" || value === null) return false;
  const card = value as Record<string, unknown>;
  return (
    typeof card.id === "string" &&
    OPS.has(card.op) &&
    typeof card.before_text === "string" &&
    typeof card.after_text === "string" &&
    POSITIONS.has(card.position ?? null) &&
    isNullableString(card.anchor_text ?? null) &&
    STATES.has(card.state) &&
    typeof card.cv_id === "string" &&
    typeof card.message_id === "string" &&
    // `warning` may be missing from an older server: read as null
    isNullableString(card.warning ?? null)
  );
}

/**
 * Parse the `data:` of an SSE `cards` event. Malformed JSON or entries are
 * dropped rather than breaking the stream.
 */
export function parseCardsEvent(data: string): ChangeCard[] {
  try {
    const parsed: unknown = JSON.parse(data);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isChangeCard).map((card) => ({ ...card, warning: card.warning ?? null }));
  } catch {
    return [];
  }
}
