import { getErrorMessage, isApiError } from "@/shared/api";
import type { Cv } from "@/entities/cv";
import type { AddToTrackerRequest } from "@/entities/vacancy";
import type { AddToTrackerFormValues } from "../model/schemas";
import type { AddMode } from "../model/types";
import { ADD_ERROR_MESSAGE, ALREADY_ADDED_DETAIL, SPECIFIC_ERROR_STATUSES } from "./constants";

/**
 * Id of the most recently updated CV (the default base for "Add & tailor CV"),
 * or null when there are none. ISO timestamps from the API compare as strings.
 */
export function pickMostRecentCvId(cvs: readonly Cv[]): string | null {
  let latest: Cv | null = null;
  for (const cv of cvs) {
    if (latest === null || cv.updated_at > latest.updated_at) latest = cv;
  }
  return latest?.id ?? null;
}

/** Request body from the dialog values. Only "Add & tailor CV" sends `base_cv_id`. */
export function toAddToTrackerBody(
  values: AddToTrackerFormValues,
  mode: AddMode,
  allowDuplicate: boolean,
): AddToTrackerRequest {
  return {
    company_name: values.company_name,
    role_title: values.role_title,
    notes: values.notes.trim() === "" ? null : values.notes,
    base_cv_id: mode === "tailor" && values.base_cv_id !== "" ? values.base_cv_id : null,
    allow_duplicate: allowDuplicate,
  };
}

/**
 * Inline dialog error: the server's string `detail` for 404/409 ("CV not found.",
 * "Vacancy is not in the Inbox."), else the generic message.
 */
export function getAddErrorMessage(error: unknown): string {
  return isApiError(error) && SPECIFIC_ERROR_STATUSES.has(error.status)
    ? getErrorMessage(error)
    : ADD_ERROR_MESSAGE;
}

/** 409 "Already added": the card was added meanwhile (e.g. in another tab). */
export function isAlreadyAddedError(error: unknown): boolean {
  if (!isApiError(error) || error.status !== 409) return false;
  const { body } = error;
  return (
    typeof body === "object" &&
    body !== null &&
    "detail" in body &&
    (body as { detail: unknown }).detail === ALREADY_ADDED_DETAIL
  );
}
