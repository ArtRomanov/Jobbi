import type { CSSProperties } from "react";
import { colors } from "@/shared/ui";

/** Markdown depth (1–6) → tag. The chat page owns the <h1>, so replies start at <h3>. */
export const HEADING_TAGS = {
  1: "h3",
  2: "h4",
  3: "h5",
  4: "h6",
  5: "h6",
  6: "h6",
} as const;

export type MarkdownDepth = keyof typeof HEADING_TAGS;

/** Chat-bubble sized: a heading is only a little larger than body text. */
export const HEADING_FONT_SIZES: Record<MarkdownDepth, string> = {
  1: "1.05rem",
  2: "1rem",
  3: "0.9375rem",
  4: "0.875rem",
  5: "0.875rem",
  6: "0.875rem",
};

export const ROOT_STYLE: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "0.5rem",
};

export const BLOCK_STYLE: CSSProperties = { margin: 0 };

export const LIST_STYLE: CSSProperties = { margin: 0, paddingLeft: "1.25rem" };

export const QUOTE_STYLE: CSSProperties = {
  margin: 0,
  paddingLeft: "0.75rem",
  borderLeft: `3px solid ${colors.border}`,
  color: colors.textSecondary,
  display: "flex",
  flexDirection: "column",
  gap: "0.5rem",
};

const MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

export const INLINE_CODE_STYLE: CSSProperties = {
  fontFamily: MONO,
  fontSize: "0.8125rem",
  padding: "0.05rem 0.3rem",
  borderRadius: "0.25rem",
  backgroundColor: colors.bgCard,
};

export const CODE_BLOCK_STYLE: CSSProperties = {
  margin: 0,
  padding: "0.5rem 0.75rem",
  borderRadius: "0.375rem",
  backgroundColor: colors.bgCard,
  border: `1px solid ${colors.borderLight}`,
  fontFamily: MONO,
  fontSize: "0.8125rem",
  whiteSpace: "pre-wrap",
  overflowX: "auto",
};

export const RULE_STYLE: CSSProperties = {
  width: "100%",
  margin: "0.25rem 0",
  border: 0,
  borderTop: `1px solid ${colors.border}`,
};

/** Unsupported markup (raw HTML, tables, …) is shown exactly as typed. */
export const RAW_STYLE: CSSProperties = { margin: 0, whiteSpace: "pre-wrap" };

export const NEW_TAB_SUFFIX = " (opens in new tab)";
