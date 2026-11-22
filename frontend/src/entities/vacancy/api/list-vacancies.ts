import { apiClient } from "@/shared/api";
import type { VacancyListParams, VacancyPage } from "../model/types";

/**
 * One page of the user's Inbox cards (new + seen by default, newest first).
 * `params.source` filters by source key ("<kind>:<handle>"), not by label.
 */
export async function listVacancies(params: VacancyListParams = {}): Promise<VacancyPage> {
  const searchParams = new URLSearchParams();
  if (params.source) searchParams.set("source", params.source);
  if (params.state) searchParams.set("state", params.state);
  if (params.sort) searchParams.set("sort", params.sort);
  if (params.page) searchParams.set("page", String(params.page));
  if (params.per_page) searchParams.set("per_page", String(params.per_page));

  const query = searchParams.toString();
  return apiClient.get<VacancyPage>(`/api/v1/vacancies${query ? `?${query}` : ""}`);
}
