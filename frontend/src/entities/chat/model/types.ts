import type { components } from "@/shared/api";

type GeneratedChangeCard = components["schemas"]["ChangeCardRead"];

/**
 * One proposed CV text edit (spec 011 §2.7), as generated from the backend.
 * `warning` (backlog #27) is declared here as well: `schema.d.ts` is generated
 * locally and not committed, so the type must not depend on a fresh regen.
 * It matches the API field; the `Omit` keeps the two from conflicting.
 */
export interface ChangeCard extends Omit<GeneratedChangeCard, "warning"> {
  /** Why the user may want to check this change before accepting; null when none. */
  warning: string | null;
}

export type ChangeCardOp = ChangeCard["op"];

export type ChangeCardState = ChangeCard["state"];

export type ChangeCardPosition = NonNullable<ChangeCard["position"]>;

/**
 * The generated ChatMessageRead schema. `cards` is always present: empty for
 * user messages and for replies without CV edits.
 */
export interface ChatMessage extends Omit<components["schemas"]["ChatMessageRead"], "cards"> {
  cards: ChangeCard[];
}
