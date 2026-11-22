import { apiClient } from "@/shared/api";
import type { VacancySource } from "../model/types";

/**
 * Add a source from raw user input (`@name`, `t.me/name`, a job-board link).
 * The server parses and checks it live; 400/409 carry a user-facing `detail`.
 */
export async function addVacancySource(input: string): Promise<VacancySource> {
  return apiClient.post<VacancySource>("/api/v1/vacancy-sources", { input });
}
