import { memo, useRef, type FocusEvent } from "react";
import { Link } from "react-router-dom";
import { colors } from "./theme";
import type { ToastData, ToastType } from "./toast-types";

const BACKGROUNDS: Record<ToastType, string> = {
  success: colors.success,
  error: colors.errorBg,
  info: colors.textPrimary,
};

const CONTROL_STYLE = {
  marginLeft: "auto",
  padding: "0.125rem 0.5rem",
  border: "1px solid rgba(255, 255, 255, 0.7)",
  borderRadius: "0.25rem",
  background: "transparent",
  color: "#ffffff",
  fontSize: "0.8125rem",
  fontWeight: 600,
  textDecoration: "none",
  cursor: "pointer",
} as const;

interface ToastItemProps {
  toast: ToastData;
  onClose: (id: number) => void;
  /** Stop the auto-close timer (hover or focus inside the toast). */
  onPause: (id: number) => void;
  /** Restart it with the time that was left. */
  onResume: (id: number) => void;
}

/**
 * One toast: message plus an optional action button and/or link. Its timer
 * is paused while the pointer is over it or focus is inside it.
 */
export const ToastItem = memo(function ToastItem({
  toast,
  onClose,
  onPause,
  onResume,
}: ToastItemProps) {
  const { id, message, type, action, link } = toast;
  const isHoveredRef = useRef(false);
  const isFocusedRef = useRef(false);

  function update(): void {
    if (isHoveredRef.current || isFocusedRef.current) onPause(id);
    else onResume(id);
  }

  function handleBlur(event: FocusEvent<HTMLDivElement>): void {
    // Focus moving between the toast's own controls keeps it paused
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
    isFocusedRef.current = false;
    update();
  }

  return (
    <div
      onMouseEnter={() => {
        isHoveredRef.current = true;
        update();
      }}
      onMouseLeave={() => {
        isHoveredRef.current = false;
        update();
      }}
      onFocus={() => {
        isFocusedRef.current = true;
        update();
      }}
      onBlur={handleBlur}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.75rem",
        padding: "0.75rem 1rem",
        borderRadius: "0.375rem",
        color: "#ffffff",
        fontSize: "0.875rem",
        backgroundColor: BACKGROUNDS[type],
        boxShadow: "0 4px 6px rgba(0, 0, 0, 0.1)",
        minWidth: "250px",
      }}
    >
      <span>{message}</span>
      {link ? (
        <Link to={link.to} onClick={() => onClose(id)} style={CONTROL_STYLE}>
          {link.label}
        </Link>
      ) : null}
      {action ? (
        <button
          type="button"
          onClick={() => {
            onClose(id);
            action.onClick();
          }}
          style={CONTROL_STYLE}
        >
          {action.label}
        </button>
      ) : null}
    </div>
  );
});
