import { useId } from "react";
import { Button, Modal, colors } from "@/shared/ui";
import {
  UNSAVED_CHANGES_LEAVE_LABEL,
  UNSAVED_CHANGES_MESSAGE,
  UNSAVED_CHANGES_STAY_LABEL,
} from "../config";

interface UnsavedChangesDialogProps {
  onLeave: () => void;
  /** Also Escape and a backdrop click: staying is the safe default. */
  onStay: () => void;
}

/** "Leave without saving?" prompt shown while a navigation is blocked. */
export function UnsavedChangesDialog({ onLeave, onStay }: UnsavedChangesDialogProps) {
  const textId = useId();

  return (
    <Modal title="Unsaved changes" onClose={onStay} describedBy={textId} maxWidth="26rem">
      <p
        id={textId}
        style={{ margin: "0 0 1.25rem", fontSize: "0.875rem", color: colors.textSecondary }}
      >
        {UNSAVED_CHANGES_MESSAGE}
      </p>
      <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
        <Button type="button" variant="secondary" onClick={onLeave}>
          {UNSAVED_CHANGES_LEAVE_LABEL}
        </Button>
        <Button type="button" onClick={onStay}>
          {UNSAVED_CHANGES_STAY_LABEL}
        </Button>
      </div>
    </Modal>
  );
}
