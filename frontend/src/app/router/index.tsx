import { Navigate, Outlet, type RouteObject } from "react-router-dom";
import { useAuthStore } from "@/features/auth";
import { LoginPage } from "@/pages/login";
import { RegisterPage } from "@/pages/register";
import { ForgotPasswordPage } from "@/pages/forgot-password";
import { ResetPasswordPage } from "@/pages/reset-password";
import { DashboardPage } from "@/pages/dashboard";
import { NewApplicationPage } from "@/pages/new-application";
import { SettingsPage } from "@/pages/settings";
import { CvsPage } from "@/pages/cvs";
import { CvEditorPage } from "@/pages/cv-editor";
import { ChatPage } from "@/pages/chat";
import { MetricsPage } from "@/pages/metrics";
import { InboxPage } from "@/pages/inbox";
import { Layout } from "@/app/layout";
import { ToastProvider } from "@/shared/ui";
import type { ReactNode } from "react";

function ProtectedRoute({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

/**
 * Root route element. ToastProvider has to sit inside the router because
 * toasts render `<Link>`; with a data router, "inside" means a route element.
 */
function AppRoot() {
  return (
    <ToastProvider>
      <Outlet />
    </ToastProvider>
  );
}

/** The app's route table: `createBrowserRouter` in the app, `createMemoryRouter` in tests. */
export const appRoutes: RouteObject[] = [
  {
    element: <AppRoot />,
    children: [
      { path: "/login", element: <LoginPage /> },
      { path: "/register", element: <RegisterPage /> },
      { path: "/forgot-password", element: <ForgotPasswordPage /> },
      { path: "/reset-password", element: <ResetPasswordPage /> },

      // Protected routes wrapped in the app shell layout
      {
        element: (
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        ),
        children: [
          { path: "/dashboard", element: <DashboardPage /> },
          { path: "/metrics", element: <MetricsPage /> },
          { path: "/inbox", element: <InboxPage /> },
          { path: "/new-application", element: <NewApplicationPage /> },
          { path: "/cvs", element: <CvsPage /> },
          { path: "/cvs/new", element: <CvEditorPage /> },
          { path: "/cvs/:id/edit", element: <CvEditorPage /> },
          { path: "/settings", element: <SettingsPage /> },
          { path: "/applications/:id/chat", element: <ChatPage /> },
        ],
      },

      // Default: redirect to dashboard (which redirects to login if not authed)
      { path: "*", element: <Navigate to="/dashboard" replace /> },
    ],
  },
];
