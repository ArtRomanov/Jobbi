import { useCallback, useRef, useState } from "react";
import type { KeyboardEvent, ChangeEvent } from "react";
import { colors, fonts } from "@/shared/ui";

interface ChatInputProps {
  onSend: (content: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled = false }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;

    onSend(trimmed);
    setValue("");

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [value, disabled, onSend]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const handleChange = useCallback((e: ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);

    // Auto-grow textarea
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, []);

  return (
    <div
      style={{
        display: "flex",
        gap: "0.5rem",
        alignItems: "flex-end",
        padding: "0.75rem 1rem",
        borderTop: `1px solid ${colors.borderLight}`,
        backgroundColor: colors.bgCard,
      }}
    >
      <textarea
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder="Type a message..."
        rows={1}
        aria-label="Chat message"
        style={{
          flex: 1,
          resize: "none",
          border: `1px solid ${colors.border}`,
          borderRadius: "0.5rem",
          padding: "0.5rem 0.75rem",
          fontFamily: fonts.base,
          fontSize: "0.875rem",
          lineHeight: 1.5,
          outline: "none",
          backgroundColor: disabled ? colors.bgDisabled : colors.bgCard,
          color: colors.textPrimary,
          maxHeight: "10rem",
          boxSizing: "border-box",
        }}
      />
      <button
        onClick={handleSend}
        disabled={disabled || !value.trim()}
        aria-label="Send message"
        style={{
          padding: "0.5rem 1rem",
          backgroundColor: colors.primary,
          color: "#ffffff",
          border: "none",
          borderRadius: "0.5rem",
          fontSize: "0.875rem",
          fontWeight: 500,
          cursor: disabled || !value.trim() ? "not-allowed" : "pointer",
          opacity: disabled || !value.trim() ? 0.6 : 1,
          flexShrink: 0,
        }}
      >
        Send
      </button>
    </div>
  );
}
