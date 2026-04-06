import { apiClient } from "@/shared/api";

export async function clearChatHistory(
  applicationId: string,
): Promise<{ message: string }> {
  return apiClient.delete<{ message: string }>(
    `/api/v1/applications/${applicationId}/chat`,
  );
}
