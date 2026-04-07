import { Link, Outlet, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/features/auth";
import { apiClient } from "@/shared/api";
import { colors, fonts } from "@/shared/ui";
import { useCallback } from "react";

/**
 * App shell layout — top navigation bar wrapping all protected routes.
 * Lives in the app layer because it composes features/auth (logout action)
 * and uses react-router Outlet for nested route rendering.
 */
export function Layout() {
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  const handleLogout = useCallback(async () => {
    try {
      await apiClient.post("/api/v1/auth/logout", {});
    } catch {
      // Proceed with client-side logout even if the API call fails
    }
    logout();
    navigate("/login");
  }, [logout, navigate]);

  return (
    <div
      style={{
        minHeight: "100vh",
        backgroundColor: colors.bgPage,
        fontFamily: fonts.base,
      }}
    >
      <header
        style={{
          backgroundColor: colors.bgCard,
          borderBottom: `1px solid ${colors.borderLight}`,
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
              color: colors.textPrimary,
              textDecoration: "none",
              marginRight: "auto",
            }}
          >
            Jobbi
          </Link>

          <Link
            to="/new-application"
            style={{
              fontSize: "0.875rem",
              color: colors.primary,
              textDecoration: "none",
              fontWeight: 500,
            }}
          >
            + New Application
          </Link>

          <Link
            to="/cvs"
            style={{
              fontSize: "0.875rem",
              color: colors.textSecondary,
              textDecoration: "none",
            }}
          >
            CVs
          </Link>

          <Link
            to="/metrics"
            style={{
              fontSize: "0.875rem",
              color: colors.textSecondary,
              textDecoration: "none",
            }}
          >
            Metrics
          </Link>

          <Link
            to="/dashboard"
            style={{
              fontSize: "0.875rem",
              color: colors.textSecondary,
              textDecoration: "none",
            }}
          >
            Dashboard
          </Link>

          <Link
            to="/settings"
            style={{
              fontSize: "0.875rem",
              color: colors.textSecondary,
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
              border: `1px solid ${colors.border}`,
              backgroundColor: colors.bgCard,
              color: colors.textSecondary,
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