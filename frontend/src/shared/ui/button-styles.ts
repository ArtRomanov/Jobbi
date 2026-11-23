import type { CSSProperties } from "react";
import { colors } from "./theme";

export type ButtonVariant = "primary" | "secondary";

const VARIANT_STYLES: Record<ButtonVariant, CSSProperties> = {
  primary: {
    backgroundColor: colors.primary,
    color: "#ffffff",
    border: "none",
  },
  secondary: {
    backgroundColor: colors.bgCard,
    color: colors.textSecondary,
    border: `1px solid ${colors.border}`,
  },
};

/** The look shared by `Button` and `ButtonLink` (a link styled as a button). */
export function getButtonStyle(
  variant: ButtonVariant,
  isDisabled = false,
): CSSProperties {
  return {
    display: "inline-block",
    padding: "0.5rem 1rem",
    borderRadius: "0.375rem",
    fontSize: "0.875rem",
    fontWeight: 500,
    lineHeight: "normal",
    textDecoration: "none",
    cursor: isDisabled ? "not-allowed" : "pointer",
    opacity: isDisabled ? 0.6 : 1,
    ...VARIANT_STYLES[variant],
  };
}
