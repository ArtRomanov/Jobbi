import type { Kpi } from "@/entities/metrics";
import { colors } from "@/shared/ui";

interface KpiCardsProps {
  kpis: Kpi;
}

interface CardProps {
  label: string;
  value: string;
}

function Card({ label, value }: CardProps) {
  return (
    <div
      style={{
        flex: 1,
        minWidth: 0,
        backgroundColor: colors.bgCard,
        padding: "1rem 1.25rem",
        borderRadius: "0.5rem",
        boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
        border: `1px solid ${colors.borderLight}`,
      }}
    >
      <div
        style={{
          fontSize: "0.75rem",
          color: colors.textMuted,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          marginBottom: "0.375rem",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: "1.75rem",
          fontWeight: 700,
          color: colors.textPrimary,
        }}
      >
        {value}
      </div>
    </div>
  );
}

export function KpiCards({ kpis }: KpiCardsProps) {
  const responseRate = `${(kpis.response_rate * 100).toFixed(0)}%`;

  return (
    <div
      style={{
        display: "flex",
        gap: "1rem",
        flexWrap: "wrap",
      }}
    >
      <Card label="Total Applications" value={String(kpis.total_applications)} />
      <Card label="Active" value={String(kpis.active)} />
      <Card label="Response Rate" value={responseRate} />
      <Card label="Interviews" value={String(kpis.interviews)} />
    </div>
  );
}
