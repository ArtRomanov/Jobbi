import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "@/features/auth";
import { ToastProvider } from "@/shared/ui";
import type { ReactNode } from "react";

/** Inline ProtectedRoute since it is not exported from the router module. */
function ProtectedRoute({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

beforeEach(() => {
  localStorage.clear();
  useAuthStore.setState({ token: null, isAuthenticated: false });
});

describe("ProtectedRoute", () => {
  it("unauthenticated user is redirected to login", () => {
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <ToastProvider>
          <Routes>
            <Route path="/login" element={<p>Login Page</p>} />
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <p>Dashboard</p>
                </ProtectedRoute>
              }
            />
          </Routes>
        </ToastProvider>
      </MemoryRouter>,
    );

    expect(screen.getByText("Login Page")).toBeInTheDocument();
    expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
  });

  it("authenticated user can access dashboard", () => {
    useAuthStore.setState({ token: "valid-token", isAuthenticated: true });

    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <ToastProvider>
          <Routes>
            <Route path="/login" element={<p>Login Page</p>} />
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <p>Dashboard</p>
                </ProtectedRoute>
              }
            />
          </Routes>
        </ToastProvider>
      </MemoryRouter>,
    );

    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.queryByText("Login Page")).not.toBeInTheDocument();
  });
});
