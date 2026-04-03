import { colors } from "@/shared/ui";

/**
 * Temporary dashboard placeholder.
 * Will be replaced with the real dashboard (kanban, metrics, etc.) later.
 */
export function DashboardPage() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "60vh",
        color: colors.textPrimary,
      }}
    >
      <h1 style={{ fontSize: "2rem", fontWeight: 700, marginBottom: "0.5rem" }}>
        Welcome to Jobbi!
      </h1>
      <p style={{ fontSize: "1rem", color: colors.textMuted }}>
        Your dashboard is coming soon.
      </p>
    </div>
  );
}
