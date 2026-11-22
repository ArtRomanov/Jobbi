import { apiClient } from "@/shared/api";
import type { AddToTrackerRequest, AddToTrackerResponse } from "../model/types";

/**
 * Creates an application (Researching, with the card's job link) from an Inbox
 * card and, with `base_cv_id`, a linked CV copy. The card becomes "added".
 *
 * Errors: 404 "Vacancy not found." / "CV not found."; 409 "Already added" /
 * "Vacancy is not in the Inbox."; 409 with a structured `detail` when the link
 * is already tracked (see `getDuplicateApplication`); 422 validation.
 */
export async function addVacancyToTracker(
  id: string,
  body: AddToTrackerRequest,
): Promise<AddToTrackerResponse> {
  return apiClient.post<AddToTrackerResponse>(
    `/api/v1/vacancies/${encodeURIComponent(id)}/add-to-tracker`,
    body,
  );
}
