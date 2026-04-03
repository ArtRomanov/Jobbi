import { isApiError } from "./client";

export function handleApiError(
  error: unknown,
  showToast: (message: string, type: "success" | "error") => void,
  statusHandlers?: Record<number, string>,
): void {
  if (isApiError(error)) {
    const customMessage = statusHandlers?.[error.status];
    if (customMessage) {
      showToast(customMessage, "error");
    } else {
      showToast("Something went wrong. Please try again.", "error");
    }
  } else {
    showToast("Network error. Check your connection.", "error");
  }
}
