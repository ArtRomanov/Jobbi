import { colors } from "./theme";

interface EmptyStateProps {
  title: string;
  description?: string;
}

/** Placeholder for a list or page with nothing to show yet. */
export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div
      style={{
        padding: "2rem 1rem",
        textAlign: "center",
        border: `1px dashed ${colors.border}`,
        borderRadius: "0.5rem",
      }}
    >
      <p style={{ fontSize: "0.9375rem", fontWeight: 500, color: colors.textSecondary }}>
        {title}
      </p>
      {description ? (
        <p style={{ marginTop: "0.25rem", fontSize: "0.875rem", color: colors.textMuted }}>
          {description}
        </p>
      ) : null}
    </div>
  );
}
