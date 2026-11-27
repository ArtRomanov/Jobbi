import type { ChangeCard } from "@/entities/chat";

/** How many characters of the anchor line the "Added after:" label shows. */
export const ANCHOR_PREVIEW_LENGTH = 40;

function previewAnchor(anchor: string): string {
  const firstLine = anchor.trim().split("\n")[0]?.trim() ?? "";
  if (firstLine.length <= ANCHOR_PREVIEW_LENGTH) return firstLine;
  // Cut at a word boundary when there is one ("first words of the line")
  const cut = firstLine.slice(0, ANCHOR_PREVIEW_LENGTH);
  const lastSpace = cut.lastIndexOf(" ");
  const words =
    firstLine[ANCHOR_PREVIEW_LENGTH] !== " " && lastSpace > 0
      ? cut.slice(0, lastSpace)
      : cut;
  return `${words.trimEnd()}…`;
}

/** Where an insertion goes, e.g. "Added after: ## Skills". */
export function getInsertLabel(
  card: Pick<ChangeCard, "position" | "anchor_text">,
): string {
  switch (card.position) {
    case "start":
      return "Added at the start";
    case "end":
      return "Added at the end";
    case "after_line": {
      const anchor = card.anchor_text ? previewAnchor(card.anchor_text) : "";
      return anchor ? `Added after: ${anchor}` : "Added";
    }
    default:
      return "Added";
  }
}

/**
 * Shown instead of the buttons on a pending card whose reply is no longer the
 * newest message: only the latest reply's cards can be decided.
 */
export const CARD_OUTDATED_LABEL = "Outdated — newer messages below";

/**
 * The card's title, numbered within its message: "CV text — change 2", or
 * "Whole CV — change 1" for a card that replaces the whole CV.
 */
export function getCardTitle(number: number, op?: ChangeCard["op"]): string {
  const subject = op === "replace_all" ? "Whole CV" : "CV text";
  return `${subject} — change ${number}`;
}

/** Accessible name of a card action, e.g. "Accept change 2". */
export function getCardActionLabel(
  action: "Accept" | "Reject",
  number: number,
): string {
  return `${action} change ${number}`;
}

/** Visible prefix of a card's warning (readable without colour). */
export const CARD_WARNING_PREFIX = "Check before accepting: ";
