import { apiClient } from "@/shared/api";
import type { ChangeCard } from "../model/types";

function cardPath(applicationId: string, cardId: string): string {
  return `/api/v1/applications/${applicationId}/chat/cards/${cardId}`;
}

/** Apply the card to the CV. Errors come back as `{"detail": "<CODE>"}`. */
export async function acceptChangeCard(
  applicationId: string,
  cardId: string,
): Promise<ChangeCard> {
  return apiClient.post<ChangeCard>(
    `${cardPath(applicationId, cardId)}/accept`,
    undefined,
  );
}

/** Mark the card rejected; the CV does not change. */
export async function rejectChangeCard(
  applicationId: string,
  cardId: string,
): Promise<ChangeCard> {
  return apiClient.post<ChangeCard>(
    `${cardPath(applicationId, cardId)}/reject`,
    undefined,
  );
}
