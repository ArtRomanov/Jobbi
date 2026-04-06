import { colors, fonts } from "@/shared/ui";
import { formatTimeAgo } from "@/shared/lib/format-time-ago";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  createdAt?: string;
  isStreaming?: boolean;
}

const bubbleStyles = {
  user: {
    alignSelf: "flex-end" as const,
    backgroundColor: colors.primary,
    color: "#ffffff",
  },
  assistant: {
    alignSelf: "flex-start" as const,
    backgroundColor: colors.bgDisabled,
    color: colors.textPrimary,
  },
} as const;

export function MessageBubble({
  role,
  content,
  createdAt,
  isStreaming = false,
}: MessageBubbleProps) {
  const variant = bubbleStyles[role];

  return (
    <div
      style={{
        ...variant,
        maxWidth: "80%",
        padding: "0.75rem 1rem",
        borderRadius: "0.75rem",
        fontFamily: fonts.base,
        fontSize: "0.875rem",
        lineHeight: 1.5,
        boxShadow: "0 1px 2px rgba(0, 0, 0, 0.06)",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
      }}
    >
      {content}
      {isStreaming && (
        <span
          style={{
            display: "inline-block",
            width: "2px",
            height: "1em",
            backgroundColor: role === "user" ? "#ffffff" : colors.textPrimary,
            marginLeft: "2px",
            verticalAlign: "text-bottom",
            animation: "blink 1s step-end infinite",
          }}
        />
      )}
      {createdAt && (
        <div
          style={{
            marginTop: "0.375rem",
            fontSize: "0.6875rem",
            opacity: 0.7,
          }}
        >
          {formatTimeAgo(createdAt)}
        </div>
      )}
    </div>
  );
}
