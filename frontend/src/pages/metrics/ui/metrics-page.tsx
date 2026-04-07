import { useEffect, useState } from "react";
import {
  getMetrics,
  type Metrics,
  type MetricsRange,
} from "@/entities/metrics";
import {
  DateRangeSelector,
  KpiCards,
  PipelineOverview,
  TrendChart,
} from "@/features/metrics-dashboard";
import { handleApiError } from "@/shared/api";
import { colors, fonts, PageHeader, useToast } from "@/shared/ui";

export function MetricsPage() {
  const [range, setRange] = useState<MetricsRange>("30d");
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const { showToast } = useToast();

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    getMetrics(range)
      .then((data) => {
        if (!cancelled) setMetrics(data);
      })
      .catch((error: unknown) => {
        if (!cancelled) handleApiError(error, showToast);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [range, showToast]);

  const isEmpty = metrics !== null && metrics.kpis.total_applications === 0;

  return (
    <div
      style={{
        maxWidth: "960px",
        margin: "0 auto",
        padding: "1.5rem",
        fontFamily: fonts.base,
      }}
    >
      <PageHeader
        title="Metrics"
        subtitle="Track your job search progress over time"
      />

      <div style={{ marginBottom: "1.5rem" }}>
        <DateRangeSelector value={range} onChange={setRange} />
      </div>

      {isLoading && !metrics ? (
        <div
          style={{
            padding: "3rem",
            textAlign: "center",
            color: colors.textMuted,
          }}
        >
          Loading metrics...
        </div>
      ) : metrics === null ? null : isEmpty ? (
        <div
          style={{
            padding: "3rem 1.5rem",
            textAlign: "center",
            backgroundColor: colors.bgCard,
            borderRadius: "0.5rem",
            border: `1px solid ${colors.borderLight}`,
            color: colors.textMuted,
          }}
        >
          No applications yet. Add some to see your metrics here.
        </div>
      ) : (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "1.5rem",
          }}
        >
          <KpiCards kpis={metrics.kpis} />
          <PipelineOverview pipeline={metrics.pipeline} />
          <TrendChart trend={metrics.trend} />
        </div>
      )}
    </div>
  );
}
