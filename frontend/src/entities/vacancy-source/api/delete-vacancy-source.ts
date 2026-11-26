import { apiClient } from "@/shared/api";
import type { RequestOptions } from "@/shared/api";

/**
 * Stop watching a source. Vacancies already found from it stay in the Inbox.
 * `keepalive` lets the request finish when the page is being closed.
 */
export async function deleteVacancySource(id: string, options?: RequestOptions): Promise<void> {
  await apiClient.delete<null>(`/api/v1/vacancy-sources/${encodeURIComponent(id)}`, options);
}
