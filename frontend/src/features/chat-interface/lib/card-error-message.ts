import { isApiError } from "@/shared/api";

/** Spec 011 §2.7 texts for a failed card decision. */
export const CARD_ERROR_MESSAGES = {
  CARD_STALE:
    "This part of the CV has changed since the suggestion. Ask the assistant again.",
  PASSAGE_NOT_UNIQUE:
    "This text appears more than once in the CV. Ask the assistant to quote a longer part.",
  TOO_LONG: "This change would make the CV longer than 20 000 characters.",
  ACCEPT_FAILED: "Could not apply this change. Please try again.",
  REJECT_FAILED: "Could not reject this change. Please try again.",
} as const;

export type CardErrorCode =
  | "CARD_STALE"
  | "PASSAGE_NOT_UNIQUE"
  | "TOO_LONG"
  | "CARD_DECIDED";

const KNOWN_CODES: ReadonlySet<string> = new Set<CardErrorCode>([
  "CARD_STALE",
  "PASSAGE_NOT_UNIQUE",
  "TOO_LONG",
  "CARD_DECIDED",
]);

function isCardErrorCode(value: unknown): value is CardErrorCode {
  return typeof value === "string" && KNOWN_CODES.has(value);
}

/** The `{"detail": "<CODE>"}` code of a 4xx card error, or null for anything else. */
export function getCardErrorCode(error: unknown): CardErrorCode | null {
  if (!isApiError(error) || error.status >= 500) return null;
  const body = error.body;
  const detail =
    typeof body === "object" && body !== null && "detail" in body
      ? (body as { detail: unknown }).detail
      : null;
  return isCardErrorCode(detail) ? detail : null;
}
