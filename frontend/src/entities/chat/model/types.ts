import type { components } from "@/shared/api";

/** One proposed CV text edit (spec 011 §2.7), as generated from the backend. */
export type ChangeCard = components["schemas"]["ChangeCardRead"];

export type ChangeCardOp = ChangeCard["op"];

export type ChangeCardState = ChangeCard["state"];

export type ChangeCardPosition = NonNullable<ChangeCard["position"]>;

/**
 * The generated ChatMessageRead schema. `cards` is always present: empty for
 * user messages and for replies without CV edits.
 */
export type ChatMessage = components["schemas"]["ChatMessageRead"];
