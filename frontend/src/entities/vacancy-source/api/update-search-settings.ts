import { apiClient } from "@/shared/api";
import type { VacancySearchSettings, VacancySearchSettingsUpdate } from "../model/types";

/**
 * Partially update the search settings; a field left out stays unchanged.
 * Returns the server-normalized values (trimmed, empty description → null;
 * keywords also lowercased, inner whitespace collapsed, de-duped).
 * 400 carries a user-facing `detail` (limits: 50 keywords, 1–64 characters each).
 */
export async function updateSearchSettings(
  update: VacancySearchSettingsUpdate,
): Promise<VacancySearchSettings> {
  return apiClient.patch<VacancySearchSettings>("/api/v1/vacancy-search-settings", update);
}
