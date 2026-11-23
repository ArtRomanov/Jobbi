import type { ChangeCard, ChatMessage } from "@/entities/chat";

/**
 * Take a freshly loaded history, but keep a card's local state when the
 * server copy still says "pending" and the local one is decided or stale.
 *
 * A history reload can start before an Accept/Reject lands and finish after
 * it; without this, the reload would put the card back to Pending. Card
 * states only move away from pending, so a non-pending local state is never
 * older than a pending server one.
 */
export function mergeCardStates(
  local: ChatMessage[],
  fresh: ChatMessage[],
): ChatMessage[] {
  const localCards = new Map<string, ChangeCard>();
  for (const message of local) {
    for (const card of message.cards ?? []) localCards.set(card.id, card);
  }
  if (localCards.size === 0) return fresh;

  return fresh.map((message) => {
    if (!message.cards?.length) return message;
    let changed = false;
    const cards = message.cards.map((card) => {
      const mine = localCards.get(card.id);
      if (card.state === "pending" && mine && mine.state !== "pending") {
        changed = true;
        return mine;
      }
      return card;
    });
    return changed ? { ...message, cards } : message;
  });
}
