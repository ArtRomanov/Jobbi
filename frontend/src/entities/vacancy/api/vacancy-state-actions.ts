import { apiClient } from "@/shared/api";

function postAction(id: string, action: "seen" | "dismiss" | "restore"): Promise<void> {
  return apiClient.post<void>(`/api/v1/vacancies/${encodeURIComponent(id)}/${action}`, undefined);
}

/** new → seen. 204; harmless on a card that is already seen. */
export async function markVacancySeen(id: string): Promise<void> {
  await postAction(id, "seen");
}

/** new | seen → dismissed. 204; 409 when the card was already added to the tracker. */
export async function dismissVacancy(id: string): Promise<void> {
  await postAction(id, "dismiss");
}

/** dismissed → seen (the Undo of a dismiss). 204. */
export async function restoreVacancy(id: string): Promise<void> {
  await postAction(id, "restore");
}
