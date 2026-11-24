import { apiClient } from "@/shared/api";
import type { VacancySearchSettings, VacancySearchSettingsUpdate } from "../model/types";

/**
 * Partially update the search settings; a field left out stays unchanged.
 * Returns the server-normalized values (trimmed, empty description → null).
 * 400 carries a user-facing `detail` (limits).
 */
export async function updateSearchSettings(
  update: VacancySearchSettingsUpdate,
): Promise<VacancySearchSettings> {
  return apiClient.patch<VacancySearchSettings>("/api/v1/vacancy-search-settings", update);
}
