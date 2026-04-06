import { Navigate, Route, Routes } from "react-router-dom";
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
import { Layout } from "@/app/layout";
import type { ReactNode } from "react";

function ProtectedRoute({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      {/* Protected routes wrapped in the app shell layout */}
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/new-application" element={<NewApplicationPage />} />
        <Route path="/cvs" element={<CvsPage />} />
        <Route path="/cvs/new" element={<CvEditorPage />} />
        <Route path="/cvs/:id/edit" element={<CvEditorPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>

      {/* Default: redirect to dashboard (which redirects to login if not authed) */}
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
