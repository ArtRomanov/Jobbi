import { apiClient } from "@/shared/api";
import type { VacancySourcesResponse } from "../model/types";

/** Fetch the user's sources, removed source labels, search settings and discovery status. */
export async function getVacancySources(): Promise<VacancySourcesResponse> {
  return apiClient.get<VacancySourcesResponse>("/api/v1/vacancy-sources");
}
