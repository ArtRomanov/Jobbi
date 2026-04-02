import { Link, Outlet, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/features/auth";
import { useCallback } from "react";

/**
 * App shell layout — top navigation bar wrapping all protected routes.
 * Lives in the app layer because it composes features/auth (logout action)
 * and uses react-router Outlet for nested route rendering.
 */
export function Layout() {
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  const handleLogout = useCallback(() => {
    logout();
    navigate("/login");
  }, [logout, navigate]);

  return (
    <div
      style={{
        minHeight: "100vh",
        backgroundColor: "#fafafa",
        fontFamily:
          "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      }}
    >
      <header
        style={{
          backgroundColor: "#ffffff",
          borderBottom: "1px solid #e5e7eb",
          padding: "0 1.5rem",
        }}
      >
        <nav
          style={{
            maxWidth: "1024px",
            margin: "0 auto",
            display: "flex",
            alignItems: "center",
            height: "3.5rem",
            gap: "1.5rem",
          }}
        >
          <Link
            to="/dashboard"
            style={{
              fontSize: "1.125rem",
              fontWeight: 700,
              color: "#1a1a1a",
              textDecoration: "none",
              marginRight: "auto",
            }}
          >
            Jobbi
          </Link>

          <Link
            to="/dashboard"
            style={{
              fontSize: "0.875rem",
              color: "#374151",
              textDecoration: "none",
            }}
          >
            Dashboard
          </Link>

          <Link
            to="/settings"
            style={{
              fontSize: "0.875rem",
              color: "#374151",
              textDecoration: "none",
            }}
          >
            Settings
          </Link>

          <button
            onClick={handleLogout}
            style={{
              padding: "0.375rem 0.75rem",
              borderRadius: "0.375rem",
              border: "1px solid #d1d5db",
              backgroundColor: "#ffffff",
              color: "#374151",
              fontSize: "0.875rem",
              cursor: "pointer",
            }}
          >
            Log Out
          </button>
        </nav>
      </header>

      <main>
        <Outlet />
      </main>
    </div>
  );
}
