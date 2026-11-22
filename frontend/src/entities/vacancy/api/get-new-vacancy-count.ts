import { apiClient } from "@/shared/api";
import type { VacancyNewCount } from "../model/types";

/** Number of Inbox cards in state "new" (the nav badge). */
export async function getNewVacancyCount(): Promise<number> {
  const { count } = await apiClient.get<VacancyNewCount>("/api/v1/vacancies/new-count");
  return count;
}
