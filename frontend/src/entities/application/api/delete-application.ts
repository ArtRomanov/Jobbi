import { apiClient } from "@/shared/api";

export async function deleteApplication(
  id: string,
): Promise<{ message: string }> {
  return apiClient.delete<{ message: string }>(
    `/api/v1/applications/${id}`,
  );
}