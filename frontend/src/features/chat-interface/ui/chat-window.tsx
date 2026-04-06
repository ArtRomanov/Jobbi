import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/entities/chat";
import { colors } from "@/shared/ui";
import { MessageBubble } from "./message-bubble";

interface ChatWindowProps {
  messages: ChatMessage[];
  streamingContent: string | null;
  isLoading: boolean;
}

export function ChatWindow({
  messages,
  streamingContent,
  isLoading,
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
        <MessageBubble
          key={msg.id}
          role={msg.role as "user" | "assistant"}
          content={msg.content}
          createdAt={msg.created_at}
        />
      ))}

      {streamingContent !== null && (
        <MessageBubble
          role="assistant"
          content={streamingContent}
          isStreaming
        />
      )}

      <div ref={bottomRef} />
    </div>
  );
}
