import { memo } from "react";
import { colors } from "@/shared/ui";
import { CARD_WARNING_PREFIX } from "../lib/card-labels";

interface CardWarningProps {
  /** Referenced by the Accept button's `aria-describedby`. */
  id: string;
  text: string;
}

/**
 * The server's note on a change card (backlog #27), e.g. that the edit rewrites
 * wording. Informational: Accept stays enabled and the user decides. Not a live
 * region — a history load would announce every card — the Accept button points
 * at it with `aria-describedby` instead.
 */
export const CardWarning = memo(function CardWarning({ id, text }: CardWarningProps) {
  return (
    <p
      id={id}
      style={{
        margin: 0,
        padding: "0.375rem 0.5rem",
        borderRadius: "0.375rem",
        backgroundColor: colors.badge.warning.bg,
        color: colors.badge.warning.text,
        fontSize: "0.8125rem",
        whiteSpace: "pre-wrap",
        overflowWrap: "anywhere",
      }}
    >
      <strong>{CARD_WARNING_PREFIX}</strong>
      {text}
    </p>
  );
});
