import type { components } from "@/shared/api";

// ---------------------------------------------------------------------------
// Change cards (spec 011, slice 7).
// TEMPORARY local types: written against the agreed backend contract before
// the backend landed. Once `schema.d.ts` is regenerated, replace them with
// `components["schemas"]["ChangeCardRead"]` (and drop the `cards` extension
// of ChatMessage below if ChatMessageRead already carries it).
// ---------------------------------------------------------------------------

export type ChangeCardOp = "replace" | "insert" | "remove";

export type ChangeCardState = "pending" | "accepted" | "rejected" | "stale";

export type ChangeCardPosition = "start" | "end" | "after_line";

/** One proposed CV text edit, as `ChangeCardRead` from the backend. */
export interface ChangeCard {
  id: string;
  op: ChangeCardOp;
  before_text: string;
  after_text: string;
  position: ChangeCardPosition | null;
  anchor_text: string | null;
  state: ChangeCardState;
  cv_id: string;
  created_at: string;
  decided_at: string | null;
}

/**
 * The generated ChatMessageRead schema plus the cards an assistant message
 * carries (absent or empty for user messages).
 */
export type ChatMessage = components["schemas"]["ChatMessageRead"] & {
  cards?: ChangeCard[];
};
