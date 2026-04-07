import type { MetricsRange } from "@/entities/metrics";
import { colors } from "@/shared/ui";
import { RANGE_OPTIONS } from "../lib/constants";

interface DateRangeSelectorProps {
  value: MetricsRange;
  onChange: (range: MetricsRange) => void;
}

export function DateRangeSelector({ value, onChange }: DateRangeSelectorProps) {
  return (
    <div
      role="group"
      aria-label="Date range"
      style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}
    >
      {RANGE_OPTIONS.map((opt) => {
        const isActive = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            aria-pressed={isActive}
            style={{
              padding: "0.375rem 0.875rem",
              fontSize: "0.8125rem",
              fontWeight: 500,
              borderRadius: "9999px",
              border: "none",
              cursor: "pointer",
              backgroundColor: isActive ? colors.primary : colors.bgDisabled,
              color: isActive ? "#ffffff" : colors.textSecondary,
              transition: "background-color 0.15s, color 0.15s",
            }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
