import { apiClient } from "@/shared/api";

/** Stop watching a source. Vacancies already found from it stay in the Inbox. */
export async function deleteVacancySource(id: string): Promise<void> {
  await apiClient.delete<null>(`/api/v1/vacancy-sources/${encodeURIComponent(id)}`);
}
