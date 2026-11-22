import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { colors } from "./theme";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  loading?: boolean;
  variant?: "primary" | "secondary";
}

const variantStyles: Record<
  "primary" | "secondary",
  Record<string, string>
> = {
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

const VISUALLY_HIDDEN = {
  position: "absolute",
  width: "1px",
  height: "1px",
  margin: "-1px",
  padding: 0,
  overflow: "hidden",
  clip: "rect(0 0 0 0)",
  whiteSpace: "nowrap",
  border: 0,
} as const;

/** Styled button. Forwards its ref so callers can manage focus. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { children, loading = false, variant = "primary", disabled, style, ...rest },
  ref,
) {
  const isDisabled = disabled || loading;

  return (
    <button
      ref={ref}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      style={{
        padding: "0.5rem 1rem",
        borderRadius: "0.375rem",
        fontSize: "0.875rem",
        fontWeight: 500,
        cursor: isDisabled ? "not-allowed" : "pointer",
        opacity: isDisabled ? 0.6 : 1,
        ...variantStyles[variant],
        ...style,
      }}
      {...rest}
    >
      {loading ? (
        <>
          {/* Visible "Loading..." while the accessible name stays the label */}
          <span aria-hidden="true">Loading...</span>
          <span style={VISUALLY_HIDDEN}>{children}</span>
        </>
      ) : (
        children
      )}
    </button>
  );
});
