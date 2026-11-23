import { isApiError } from "@/shared/api";

/** Upload limit, mirrored from the backend (`MAX_UPLOAD_BYTES`). */
export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;

export const UPLOAD_ERROR_MESSAGES = {
  UNSUPPORTED_FILE: "Upload a PDF or DOCX file.",
  FILE_TOO_LARGE: "The file is larger than 5 MB.",
  NO_TEXT:
    "Could not read text from this file. Upload a PDF with selectable text or a DOCX.",
  UPLOAD_FAILED: "Could not upload this file. Please try again.",
} as const;

type UploadErrorCode = keyof typeof UPLOAD_ERROR_MESSAGES;

function isUploadErrorCode(value: unknown): value is UploadErrorCode {
  return (
    typeof value === "string" &&
    Object.prototype.hasOwnProperty.call(UPLOAD_ERROR_MESSAGES, value)
  );
}

/**
 * The spec text for a failed upload. The backend answers `{"detail": "<CODE>"}`;
 * anything else (network error, 401, 5xx, an unknown code) is the generic text.
 */
export function getUploadErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    const body = error.body;
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? (body as { detail: unknown }).detail
        : null;
    if (isUploadErrorCode(detail)) return UPLOAD_ERROR_MESSAGES[detail];
  }
  return UPLOAD_ERROR_MESSAGES.UPLOAD_FAILED;
}
