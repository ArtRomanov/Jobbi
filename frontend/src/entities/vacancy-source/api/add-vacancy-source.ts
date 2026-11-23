import { apiClient } from "@/shared/api";
import type { VacancySource, VacancySourceCreate } from "../model/types";

/**
 * Add a source from raw user input (`@name`, `t.me/name`, a job-board or page
 * link). Web pages also take an optional `job_link_contains` and `name`.
 * The server parses and checks it live; 400/409 carry a user-facing `detail`.
 */
export async function addVacancySource(body: VacancySourceCreate): Promise<VacancySource> {
  return apiClient.post<VacancySource>("/api/v1/vacancy-sources", body);
}
