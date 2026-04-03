import { apiClient } from "@/shared/api";
import type { Application, PaginatedResponse } from "../model/types";

export async function listApplications(params?: {
  page?: number;
  per_page?: number;
  status?: string;
  search?: string;
}): Promise<PaginatedResponse<Application>> {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.per_page) searchParams.set("per_page", String(params.per_page));
  if (params?.status) searchParams.set("status", params.status);
  if (params?.search) searchParams.set("search", params.search);

  const query = searchParams.toString();
  const path = `/api/v1/applications${query ? `?${query}` : ""}`;

  return apiClient.get<PaginatedResponse<Application>>(path);
}