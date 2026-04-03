import { apiClient } from "@/shared/api";
import type { PaginatedResponse, StatusHistoryFeed } from "../model/types";

export async function getHistory(params?: {
  page?: number;
  per_page?: number;
}): Promise<PaginatedResponse<StatusHistoryFeed>> {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.per_page) searchParams.set("per_page", String(params.per_page));

  const query = searchParams.toString();
  const path = `/api/v1/applications/history${query ? `?${query}` : ""}`;

  return apiClient.get<PaginatedResponse<StatusHistoryFeed>>(path);
}