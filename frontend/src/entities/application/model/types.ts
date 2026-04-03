import type { components } from "@/shared/api";

export type Application = components["schemas"]["ApplicationRead"];
export type ApplicationDetail = components["schemas"]["ApplicationDetailRead"];
export type ApplicationCreate = components["schemas"]["ApplicationCreate"];
export type ApplicationUpdate = components["schemas"]["ApplicationUpdate"];
export type StatusHistory = components["schemas"]["StatusHistoryRead"];
export type StatusHistoryFeed = components["schemas"]["StatusHistoryFeedRead"];

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
}