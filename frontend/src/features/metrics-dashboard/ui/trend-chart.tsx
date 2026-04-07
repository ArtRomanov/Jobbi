import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TrendData } from "@/entities/metrics";
import { colors } from "@/shared/ui";

interface TrendChartProps {
  trend: TrendData;
}

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const month = MONTHS[date.getMonth()] ?? "";
  const day = date.getDate();
  const yr = date.getFullYear() % 100;
  return `${month} ${String(day)}, ${String(yr).padStart(2, "0")}`;
}

export function TrendChart({ trend }: TrendChartProps) {
  const hasData =
    trend.points.length > 0 && trend.points.some((p) => p.count > 0);

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
        Applications over time
      </h2>
      {hasData ? (
        <div style={{ width: "100%", height: 280 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={trend.points}
              margin={{ top: 8, right: 16, bottom: 8, left: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke={colors.borderLight} />
              <XAxis
                dataKey="date"
                tickFormatter={formatDate}
                stroke={colors.textMuted}
                fontSize={12}
              />
              <YAxis
                stroke={colors.textMuted}
                fontSize={12}
                allowDecimals={false}
              />
              <Tooltip
                labelFormatter={(label) => formatDate(String(label))}
              />
              <Line
                type="monotone"
                dataKey="count"
                stroke={colors.primary}
                strokeWidth={2}
                dot={{ fill: colors.primary, r: 3 }}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div
          style={{
            padding: "3rem 1rem",
            textAlign: "center",
            color: colors.textMuted,
            fontSize: "0.875rem",
          }}
        >
          No applications in this period
        </div>
      )}
    </div>
  );
}
