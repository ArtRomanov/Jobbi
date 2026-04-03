import { apiClient } from "@/shared/api";
import type { ApplicationDetail } from "../model/types";

export async function getApplication(id: string): Promise<ApplicationDetail> {
  return apiClient.get<ApplicationDetail>(`/api/v1/applications/${id}`);
}