import type { ReactNode } from "react";
import { colors, fonts } from "./theme";

interface AuthLayoutProps {
  maxWidth?: string;
  children: ReactNode;
}

/**
 * Full-screen centered layout for authentication pages (login, register, etc.).
 * Provides a card container with consistent styling across all auth flows.
 */
export function AuthLayout({ maxWidth = "400px", children }: AuthLayoutProps) {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: colors.bgPage,
        fontFamily: fonts.base,
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth,
          padding: "2rem",
          backgroundColor: colors.bgCard,
          borderRadius: "0.5rem",
          boxShadow: "0 1px 3px rgba(0, 0, 0, 0.1)",
        }}
      >
        {children}
      </div>
    </div>
  );
}
