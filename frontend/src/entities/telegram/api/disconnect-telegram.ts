import { apiClient } from "@/shared/api";

/** Remove the Telegram link from the current user's account. */
export async function disconnectTelegram(): Promise<{ message: string }> {
  return apiClient.delete<{ message: string }>("/api/v1/telegram/link");
}
