/**
 * Shared color palette and design tokens for the Jobbi app.
 * Import from @/shared/ui and use instead of hardcoded hex values.
 */

export const colors = {
  // Brand
  primary: "#2563eb",
  primaryHover: "#1d4ed8",

  // Text
  textPrimary: "#1a1a1a",
  textSecondary: "#374151",
  textMuted: "#6b7280",
  textPlaceholder: "#9ca3af",

  // Backgrounds
  bgPage: "#fafafa",
  bgCard: "#ffffff",
  bgDisabled: "#f3f4f6",

  // Borders
  border: "#d1d5db",
  borderLight: "#e5e7eb",

  // Feedback
  error: "#ef4444",
  errorBg: "#dc2626",
  success: "#16a34a",

  // Status colors (for kanban board)
  status: {
    researching: "#6366f1",
    applied: "#2563eb",
    interview: "#f59e0b",
    offer: "#16a34a",
    rejected: "#ef4444",
    withdrawn: "#6b7280",
  },
} as const;

export const fonts = {
  base: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
} as const;