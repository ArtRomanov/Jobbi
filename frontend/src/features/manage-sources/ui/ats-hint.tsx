import { useRef } from "react";
import type { AtsHint as AtsHintData } from "@/entities/vacancy-source";
import { Button, colors } from "@/shared/ui";
import { ADD_BOARD_LABEL } from "../lib/constants";

interface AtsHintProps {
  hint: AtsHintData;
  /** Another preview request is running: the button is blocked. */
  busy: boolean;
  /** The board add itself is running: the button shows loading. */
  isAdding: boolean;
  /** Resolves true when the board was added; on `false` focus goes back to the button. */
  onAddBoard: (boardInput: string) => Promise<boolean>;
}

/**
 * "This page uses <Service> — add the board instead…" inside a web page
 * preview, with "Add the board" (adds the board like a pasted board link).
 */
export function AtsHint({ hint, busy, isAdding, onAddBoard }: AtsHintProps) {
  const buttonRef = useRef<HTMLButtonElement>(null);

  const handleClick = async (): Promise<void> => {
    if (busy) return;
    // The loading button was disabled (focus dropped); bring it back on failure
    if (!(await onAddBoard(hint.input))) buttonRef.current?.focus();
  };

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: "0.5rem",
        padding: "0.75rem",
        marginBottom: "1rem",
        borderRadius: "0.375rem",
        background: colors.badge.accent.bg,
      }}
    >
      <p style={{ flex: "1 1 16rem", fontSize: "0.875rem", color: colors.textPrimary }}>
        This page uses {hint.label} — add the board instead for full job texts and dates
      </p>
      <Button
        ref={buttonRef}
        type="button"
        variant="secondary"
        loading={isAdding}
        disabled={busy && !isAdding}
        onClick={() => void handleClick()}
      >
        {ADD_BOARD_LABEL}
      </Button>
    </div>
  );
}
