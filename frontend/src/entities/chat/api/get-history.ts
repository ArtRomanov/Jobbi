import { apiClient } from "@/shared/api";
import type { ChatMessage } from "../model/types";

export async function getChatHistory(
  applicationId: string,
): Promise<ChatMessage[]> {
  return apiClient.get<ChatMessage[]>(
    `/api/v1/applications/${applicationId}/chat`,
  );
}
