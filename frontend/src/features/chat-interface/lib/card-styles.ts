import type { CSSProperties } from "react";
import type { ChangeCardState } from "@/entities/chat";
import { colors } from "@/shared/ui";
import type { DiffRowKind } from "./build-diff-rows";

/** Card border colour per state (the left border is drawn wider). */
export const CARD_BORDER: Record<ChangeCardState, string> = {
  pending: colors.border,
  accepted: colors.success,
  rejected: colors.borderLight,
  stale: colors.badge.warning.text,
};

export const CARD_BUTTON_STYLE: CSSProperties = {
  fontSize: "0.75rem",
  padding: "0.25rem 0.75rem",
};

/** Marker, screen-reader prefix and colours per diff line kind (readable without colour). */
export const DIFF_ROW_KIND: Record<
  DiffRowKind,
  { marker: string; srPrefix: string | null; style: CSSProperties }
> = {
  same: { marker: " ", srPrefix: null, style: { color: colors.textSecondary } },
  removed: {
    marker: "−",
    srPrefix: "Removed line: ",
    style: {
      backgroundColor: colors.badge.danger.bg,
      color: colors.badge.danger.text,
    },
  },
  added: {
    marker: "+",
    srPrefix: "Added line: ",
    style: {
      backgroundColor: colors.badge.success.bg,
      color: colors.badge.success.text,
    },
  },
};

export const DIFF_LINE_STYLE: CSSProperties = {
  display: "flex",
  gap: "0.5rem",
  padding: "0 0.375rem",
  textDecoration: "none",
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};
