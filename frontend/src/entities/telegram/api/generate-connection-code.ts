import { apiClient } from "@/shared/api";
import type { ConnectionCode } from "../model/types";

/** Create a fresh one-time linking code (invalidates any previous one). */
export async function generateConnectionCode(): Promise<ConnectionCode> {
  return apiClient.post<ConnectionCode>("/api/v1/telegram/connection-code", {});
}
