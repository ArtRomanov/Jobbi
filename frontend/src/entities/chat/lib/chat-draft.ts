/**
 * Router state for `/applications/:id/chat`: `draft` pre-fills the message
 * input and is never sent on its own. Written by features (e.g. "Add & tailor
 * CV"), read once by the chat page.
 */
export interface ChatRouteState {
  draft: string;
}

/** The non-empty `draft` from router state, or null (state is untyped history data). */
export function getChatDraft(state: unknown): string | null {
  if (typeof state !== "object" || state === null || !("draft" in state)) return null;
  const { draft } = state as { draft: unknown };
  return typeof draft === "string" && draft.trim() !== "" ? draft : null;
}
