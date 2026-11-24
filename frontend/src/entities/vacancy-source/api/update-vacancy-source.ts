import { apiClient } from "@/shared/api";
import type { VacancySource, VacancySourceUpdate } from "../model/types";

/**
 * Partially update a source; a field left out stays unchanged. `name: null`
 * (or "") puts the default name back. Returns the updated source.
 * 400/404 carry a user-facing `detail` (e.g. "Name can be up to 100 characters").
 */
export async function updateVacancySource(
  id: string,
  patch: VacancySourceUpdate,
): Promise<VacancySource> {
  return apiClient.patch<VacancySource>(`/api/v1/vacancy-sources/${encodeURIComponent(id)}`, patch);
}
