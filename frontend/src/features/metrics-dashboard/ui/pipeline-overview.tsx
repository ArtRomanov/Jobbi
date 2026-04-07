import type { PipelineEntry } from "@/entities/metrics";
import { STATUSES, type StatusKey } from "@/entities/application";
import { colors } from "@/shared/ui";

interface PipelineOverviewProps {
  pipeline: PipelineEntry[];
}

export function PipelineOverview({ pipeline }: PipelineOverviewProps) {
  const countByStatus = new Map<string, number>();
  for (const entry of pipeline) {
    countByStatus.set(entry.status, entry.count);
  }

  const maxCount = Math.max(
    1,
    ...STATUSES.map((s) => countByStatus.get(s.key) ?? 0),
  );

  return (
    <div
      style={{
        backgroundColor: colors.bgCard,
        padding: "1.25rem 1.5rem",
        borderRadius: "0.5rem",
        border: `1px solid ${colors.borderLight}`,
        boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
      }}
    >
      <h2
        style={{
          fontSize: "1rem",
          fontWeight: 600,
          color: colors.textPrimary,
          marginTop: 0,
          marginBottom: "1rem",
        }}
      >
        Pipeline
      </h2>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.625rem",
        }}
      >
        {STATUSES.map((s) => {
          const count = countByStatus.get(s.key) ?? 0;
          const widthPct = Math.max(2, (count / maxCount) * 100);
          const color = colors.status[s.key as StatusKey];
          return (
            <div
              key={s.key}
              style={{
                display: "grid",
                gridTemplateColumns: "7rem 1fr 2rem",
                alignItems: "center",
                gap: "0.75rem",
              }}
            >
              <div
                style={{
                  fontSize: "0.8125rem",
                  color: colors.textSecondary,
                }}
              >
                {s.label}
              </div>
              <div
                style={{
                  height: "0.75rem",
                  backgroundColor: colors.bgDisabled,
                  borderRadius: "9999px",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${String(widthPct)}%`,
                    height: "100%",
                    backgroundColor: color,
                    transition: "width 0.3s",
                  }}
                />
              </div>
              <div
                style={{
                  fontSize: "0.875rem",
                  fontWeight: 600,
                  color: colors.textPrimary,
                  textAlign: "right",
                }}
              >
                {count}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
