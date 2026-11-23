import type { ReactNode } from "react";

/** Hides content visually while keeping it in the accessibility tree. */
export const VISUALLY_HIDDEN_STYLE = {
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

/** Text for screen readers only (e.g. a context prefix on a badge). */
export function VisuallyHidden({ children }: { children: ReactNode }) {
  return <span style={VISUALLY_HIDDEN_STYLE}>{children}</span>;
}
