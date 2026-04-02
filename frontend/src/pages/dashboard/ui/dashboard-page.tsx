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
        color: "#1a1a1a",
      }}
    >
      <h1 style={{ fontSize: "2rem", fontWeight: 700, marginBottom: "0.5rem" }}>
        Welcome to Jobbi!
      </h1>
      <p style={{ fontSize: "1rem", color: "#6b7280" }}>
        Your dashboard is coming soon.
      </p>
    </div>
  );
}
