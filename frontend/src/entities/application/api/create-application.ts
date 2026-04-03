import { apiClient } from "@/shared/api";
import type { ApplicationCreate, ApplicationDetail } from "../model/types";

export async function createApplication(
  data: ApplicationCreate,
): Promise<ApplicationDetail> {
  return apiClient.post<ApplicationDetail>("/api/v1/applications", data);
}