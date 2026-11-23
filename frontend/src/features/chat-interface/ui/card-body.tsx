import { useMemo } from "react";
import type { ChangeCard } from "@/entities/chat";
import { buildCardDiff, markAllLines } from "../lib/build-diff-rows";
import { getInsertLabel } from "../lib/card-labels";
import { DiffLinesView } from "./diff-lines-view";

/** The passage of a card: Before/After for replace, the added or removed lines otherwise. */
export function CardBody({ card }: { card: ChangeCard }) {
  const { op, before_text: beforeText, after_text: afterText } = card;
  const diff = useMemo(
    () => (op === "replace" ? buildCardDiff(beforeText, afterText) : null),
    [op, beforeText, afterText],
  );

  if (diff) {
    return (
      <>
        <DiffLinesView label="Before" rows={diff.before} />
        <DiffLinesView label="After" rows={diff.after} />
      </>
    );
  }
  if (op === "insert") {
    return (
      <DiffLinesView
        label={getInsertLabel(card)}
        rows={markAllLines(afterText, "added")}
      />
    );
  }
  return (
    <DiffLinesView label="Removed" rows={markAllLines(beforeText, "removed")} />
  );
}
