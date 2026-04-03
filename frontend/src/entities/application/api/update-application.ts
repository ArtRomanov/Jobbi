import { apiClient } from "@/shared/api";
import type { ApplicationDetail, ApplicationUpdate } from "../model/types";

export async function updateApplication(
  id: string,
  data: ApplicationUpdate,
): Promise<ApplicationDetail> {
  return apiClient.patch<ApplicationDetail>(
    `/api/v1/applications/${id}`,
    data,
  );
}