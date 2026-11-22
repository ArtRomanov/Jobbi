import type { HTMLAttributes, ReactNode } from "react";
import { colors } from "./theme";

export type BadgeTone = keyof typeof colors.badge;

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  children: ReactNode;
  /** Color scheme of the pill; defaults to "neutral". */
  tone?: BadgeTone;
}

/** Small rounded pill for counts, statuses and labels. */
export function Badge({ children, tone = "neutral", style, ...rest }: BadgeProps) {
  const { bg, text } = colors.badge[tone];
  return (
    <span
      {...rest}
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "0.0625rem 0.5rem",
        borderRadius: "9999px",
        backgroundColor: bg,
        color: text,
        fontSize: "0.75rem",
        fontWeight: 600,
        lineHeight: 1.5,
        whiteSpace: "nowrap",
        ...style,
      }}
    >
      {children}
    </span>
  );
}
