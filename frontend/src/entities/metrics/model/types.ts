import type { components } from "@/shared/api";

export type Metrics = components["schemas"]["MetricsResponse"];
export type Kpi = components["schemas"]["KpiData"];
export type PipelineEntry = components["schemas"]["PipelineEntry"];
export type TrendPoint = components["schemas"]["TrendPoint"];
export type TrendData = components["schemas"]["TrendData"];
export type MetricsRange = "7d" | "30d" | "90d" | "all";
