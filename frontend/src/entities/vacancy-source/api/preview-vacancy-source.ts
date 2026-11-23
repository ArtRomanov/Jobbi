import { apiClient } from "@/shared/api";
import type { VacancySourcePreview, VacancySourcePreviewRequest } from "../model/types";

/**
 * Check what a raw input would become, without saving anything. Non-web kinds
 * answer with `{kind}` only (no network); a web page is opened and its first
 * listing page counted. 400/409 carry a user-facing `detail`.
 */
export async function previewVacancySource(
  body: VacancySourcePreviewRequest,
): Promise<VacancySourcePreview> {
  return apiClient.post<VacancySourcePreview>("/api/v1/vacancy-sources/preview", body);
}
