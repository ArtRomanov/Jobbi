import type { ChangeCard, ChatMessage } from "@/entities/chat";

/**
 * Messages with `card` swapped in by id. Messages without that card keep
 * their identity, so their memoized cards do not re-render.
 */
export function replaceCardInMessages(
  messages: ChatMessage[],
  card: ChangeCard,
): ChatMessage[] {
  return messages.map((message) =>
    message.cards?.some((c) => c.id === card.id)
      ? {
          ...message,
          cards: message.cards.map((c) => (c.id === card.id ? card : c)),
        }
      : message,
  );
}
