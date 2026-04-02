import { useAuthStore } from "@/features/auth";

/**
 * Temporary dashboard placeholder.
 * Will be replaced with the real dashboard (kanban, metrics, etc.) later.
 */
export function DashboardPage() {
  const logout = useAuthStore((s) => s.logout);

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        fontFamily:
          "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        backgroundColor: "#fafafa",
        color: "#1a1a1a",
      }}
    >
      <h1 style={{ fontSize: "2rem", fontWeight: 700, marginBottom: "0.5rem" }}>
        Welcome to Jobbi!
      </h1>
      <p style={{ fontSize: "1rem", color: "#6b7280", marginBottom: "2rem" }}>
        Your dashboard is coming soon.
      </p>
      <button
        onClick={logout}
        style={{
          padding: "0.5rem 1rem",
          borderRadius: "0.375rem",
          border: "1px solid #d1d5db",
          backgroundColor: "#ffffff",
          color: "#374151",
          fontSize: "0.875rem",
          cursor: "pointer",
        }}
      >
        Log out
      </button>
    </div>
  );
}
