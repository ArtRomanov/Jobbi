import { apiClient } from "@/shared/api";
import type { Metrics, MetricsRange } from "../model/types";

export function getMetrics(range: MetricsRange): Promise<Metrics> {
  return apiClient.get<Metrics>(`/api/v1/metrics?range=${range}`);
}
