import type { ButtonHTMLAttributes, ReactNode } from "react";

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
    backgroundColor: "#2563eb",
    color: "#ffffff",
    border: "none",
  },
  secondary: {
    backgroundColor: "#ffffff",
    color: "#374151",
    border: "1px solid #d1d5db",
  },
};

export function Button({
  children,
  loading = false,
  variant = "primary",
  disabled,
  style,
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading;

  return (
    <button
      disabled={isDisabled}
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
      {loading ? "Loading..." : children}
    </button>
  );
}
