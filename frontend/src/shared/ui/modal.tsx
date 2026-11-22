import {
  useEffect,
  useId,
  useRef,
  useState,
  type FocusEvent,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { getFirstField, getFocusableElements } from "@/shared/lib";
import { isTopModal, pushModal, removeModal } from "./modal-stack";
import { colors } from "./theme";

interface ModalProps {
  /** Visible heading; also the dialog's accessible name. */
  title: string;
  /** Escape, a backdrop click, or the caller's own Cancel button. */
  onClose: () => void;
  children: ReactNode;
  /** False blocks Escape and backdrop clicks (e.g. while a request runs). Defaults to true. */
  isDismissable?: boolean;
  /** Id of an element inside that describes the dialog (`aria-describedby`). */
  describedBy?: string;
  maxWidth?: string;
}

/**
 * Modal dialog (WAI-ARIA dialog pattern). Render it only while it is open:
 * mounting moves focus to the first form field (else the first focusable
 * element, else the dialog), focus cannot leave it (Tab wraps, focus landing
 * outside or on nothing is pulled back), Escape and a backdrop click call
 * `onClose`, and unmounting returns focus to the element that had it before,
 * if that element is still on the page. Nested modals: only the top one
 * reacts; Escape never reaches document listeners (e.g. a drawer below).
 */
export function Modal({
  title,
  onClose,
  children,
  isDismissable = true,
  describedBy,
  maxWidth = "32rem",
}: ModalProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  // Identity in the modal stack; stable for the component's life
  const [token] = useState(() => ({}));
  // Close on a click only when it also started on the backdrop (not a text selection dragged out)
  const pressStartedOnBackdropRef = useRef(false);

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = dialogRef.current;
    pushModal(token);
    if (dialog) (getFirstField(dialog) ?? getFocusableElements(dialog)[0] ?? dialog).focus();

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function handleFocusIn(event: globalThis.FocusEvent): void {
      if (!dialog || !isTopModal(token)) return;
      if (event.target instanceof Node && dialog.contains(event.target)) return;
      (getFocusableElements(dialog)[0] ?? dialog).focus();
    }
    document.addEventListener("focusin", handleFocusIn);

    return () => {
      document.removeEventListener("focusin", handleFocusIn);
      removeModal(token);
      document.body.style.overflow = previousOverflow;
      if (opener?.isConnected) opener.focus();
    };
  }, [token]);

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    if (event.key === "Escape") {
      // Never let a drawer or page listener below also handle it
      event.stopPropagation();
      event.preventDefault();
      if (isDismissable && isTopModal(token)) onClose();
      return;
    }
    if (event.key !== "Tab") return;
    const dialog = event.currentTarget;
    const focusable = getFocusableElements(dialog);
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!first || !last) {
      event.preventDefault();
      return;
    }
    const active = document.activeElement;
    if (event.shiftKey && (active === first || active === dialog)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  // Focus dropped to <body> (e.g. the focused button became disabled): take it back
  function handleBlur(event: FocusEvent<HTMLDivElement>): void {
    if (event.relatedTarget !== null) return;
    const dialog = event.currentTarget;
    setTimeout(() => {
      if (!dialog.isConnected || !isTopModal(token)) return;
      const active = document.activeElement;
      if (active === null || active === document.body) dialog.focus();
    }, 0);
  }

  function handleBackdropMouseDown(event: MouseEvent<HTMLDivElement>): void {
    const isOnBackdrop = event.target === event.currentTarget;
    // Keeps focus where it is (inside the dialog) instead of moving it to <body>
    if (isOnBackdrop) event.preventDefault();
    pressStartedOnBackdropRef.current = isOnBackdrop;
  }

  function handleBackdropClick(event: MouseEvent<HTMLDivElement>): void {
    const isBackdropClick = pressStartedOnBackdropRef.current && event.target === event.currentTarget;
    pressStartedOnBackdropRef.current = false;
    if (isBackdropClick && isDismissable) onClose();
  }

  return createPortal(
    <div
      data-testid="modal-backdrop"
      onMouseDown={handleBackdropMouseDown}
      onClick={handleBackdropClick}
      style={{
        position: "fixed",
        inset: 0,
        // Above the application drawer (1001)
        zIndex: 1100,
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        padding: "2rem 1rem",
        overflowY: "auto",
        backgroundColor: "rgba(0, 0, 0, 0.4)",
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={describedBy}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        onBlur={handleBlur}
        style={{
          width: "100%",
          maxWidth,
          padding: "1.25rem",
          borderRadius: "0.5rem",
          backgroundColor: colors.bgCard,
          boxShadow: "0 10px 25px rgba(0, 0, 0, 0.2)",
          outline: "none",
          boxSizing: "border-box",
        }}
      >
        <h2
          id={titleId}
          style={{ margin: "0 0 1rem", fontSize: "1.125rem", fontWeight: 600, color: colors.textPrimary }}
        >
          {title}
        </h2>
        {children}
      </div>
    </div>,
    document.body,
  );
}
