import { isApiError } from "@/shared/api";
import {
  CV_CHANGED_ELSEWHERE_MESSAGE,
  CV_CHANGED_ERROR_CODE,
  CV_SAVE_FAILED_MESSAGE,
} from "../config";

/**
 * What the editor shows when a save fails: the "changed elsewhere" text for
 * the PATCH 409 `CV_CHANGED` (a stale `version`), else the generic save error.
 */
export function getCvSaveErrorMessage(error: unknown): string {
  if (
    isApiError(error) &&
    error.status === 409 &&
    typeof error.body === "object" &&
    error.body !== null &&
    "detail" in error.body &&
    (error.body as { detail: unknown }).detail === CV_CHANGED_ERROR_CODE
  ) {
    return CV_CHANGED_ELSEWHERE_MESSAGE;
  }
  return CV_SAVE_FAILED_MESSAGE;
}
