import { isApiError } from "./client";

export const GENERIC_ERROR_MESSAGE = "Something went wrong. Please try again.";
export const NETWORK_ERROR_MESSAGE = "Network error. Check your connection.";

/**
 * The user-facing message the backend put in `{"detail": "<message>"}`.
 * Only client errors (4xx) are trusted: a 5xx body may carry internals.
 */
function getStringDetail(status: number, body: unknown): string | null {
  if (status < 400 || status >= 500) return null;
  if (typeof body !== "object" || body === null || !("detail" in body)) return null;
  const { detail } = body as { detail: unknown };
  return typeof detail === "string" && detail.trim() !== "" ? detail : null;
}

/** First message of a FastAPI 422 body: `{"detail": [{"msg": "..."}]}`. */
function getValidationMessage(body: unknown): string | null {
  if (typeof body !== "object" || body === null || !("detail" in body)) return null;
  const { detail } = body as { detail: unknown };
  if (!Array.isArray(detail) || detail.length === 0) return null;
  const first: unknown = detail[0];
  if (typeof first !== "object" || first === null || !("msg" in first)) return null;
  const { msg } = first as { msg: unknown };
  return typeof msg === "string" && msg.trim() !== "" ? msg : null;
}

/**
 * Message for an inline (non-toast) error, e.g. under an input.
 * Order: string `detail` (4xx) → first 422 validation message → generic;
 * anything that is not an ApiError counts as a network failure.
 */
export function getErrorMessage(error: unknown): string {
  if (!isApiError(error)) return NETWORK_ERROR_MESSAGE;
  return (
    getStringDetail(error.status, error.body) ??
    getValidationMessage(error.body) ??
    GENERIC_ERROR_MESSAGE
  );
}

/**
 * Show an API error as a toast. The caller's `statusHandlers[status]` wins;
 * otherwise a string `detail` from a 4xx response, otherwise a generic message.
 */
export function handleApiError(
  error: unknown,
  showToast: (message: string, type: "success" | "error") => void,
  statusHandlers?: Record<number, string>,
): void {
  if (!isApiError(error)) {
    showToast(NETWORK_ERROR_MESSAGE, "error");
    return;
  }
  const message =
    statusHandlers?.[error.status] ??
    getStringDetail(error.status, error.body) ??
    GENERIC_ERROR_MESSAGE;
  showToast(message, "error");
}
