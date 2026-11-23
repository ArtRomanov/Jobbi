import { Fragment, useEffect, useRef } from "react";
import type { ChangeCard, ChatMessage } from "@/entities/chat";
import { colors } from "@/shared/ui";
import { CardList } from "./card-list";
import { MessageBubble } from "./message-bubble";

interface ChatWindowProps {
  applicationId: string;
  messages: ChatMessage[];
  streamingContent: string | null;
  /** Cards of the reply being streamed (the `cards` event arrives before `done`). */
  streamingCards?: ChangeCard[];
  isLoading: boolean;
  onCardUpdated: (card: ChangeCard) => void;
}

export function ChatWindow({
  applicationId,
  messages,
  streamingContent,
  streamingCards = [],
  isLoading,
  onCardUpdated,
}: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to the bottom when messages change or streaming content updates
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  return (
    <div
      style={{
        flex: 1,
        overflowY: "auto",
        padding: "1rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.75rem",
      }}
    >
      {isLoading && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flex: 1,
            color: colors.textMuted,
            fontSize: "0.875rem",
          }}
        >
          Loading chat history...
        </div>
      )}

      {!isLoading && messages.length === 0 && streamingContent === null && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flex: 1,
            color: colors.textMuted,
            fontSize: "0.875rem",
            textAlign: "center",
            padding: "2rem",
          }}
        >
          No messages yet. Send a message or use a quick action to start the
          conversation.
        </div>
      )}

      {messages.map((msg) => (
        <Fragment key={msg.id}>
          <MessageBubble
            role={msg.role as "user" | "assistant"}
            content={msg.content}
            createdAt={msg.created_at}
          />
          <CardList
            applicationId={applicationId}
            cards={msg.cards}
            onCardUpdated={onCardUpdated}
          />
        </Fragment>
      ))}

      {streamingContent !== null && (
        <>
          <MessageBubble
            role="assistant"
            content={streamingContent}
            isStreaming
          />
          <CardList
            applicationId={applicationId}
            cards={streamingCards}
            onCardUpdated={onCardUpdated}
          />
        </>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
