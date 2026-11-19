import { apiClient } from "@/shared/api";
import type { TelegramStatus } from "../model/types";

/** Fetch whether the current user has a linked Telegram account. */
export async function getTelegramStatus(): Promise<TelegramStatus> {
  return apiClient.get<TelegramStatus>("/api/v1/telegram/status");
}
