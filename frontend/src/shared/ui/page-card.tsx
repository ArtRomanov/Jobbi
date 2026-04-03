import type { ReactNode } from "react";
import { colors } from "./theme";

interface PageCardProps {
  maxWidth?: string;
  children: ReactNode;
}

/**
 * Centered card container for authenticated pages (settings, new application, etc.).
 */
export function PageCard({ maxWidth = "480px", children }: PageCardProps) {
  return (
    <div
      style={{
        maxWidth,
        margin: "2rem auto",
        padding: "2rem",
        backgroundColor: colors.bgCard,
        borderRadius: "0.5rem",
        boxShadow: "0 1px 3px rgba(0, 0, 0, 0.1)",
      }}
    >
      {children}
    </div>
  );
}
