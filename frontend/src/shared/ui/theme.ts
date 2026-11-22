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

  // Badge tones (background / text pairs, WCAG AA on the pill)
  badge: {
    neutral: { bg: "#f3f4f6", text: "#374151" },
    accent: { bg: "#dbeafe", text: "#1d4ed8" },
    success: { bg: "#dcfce7", text: "#166534" },
    warning: { bg: "#fef3c7", text: "#92400e" },
    danger: { bg: "#fee2e2", text: "#991b1b" },
  },

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