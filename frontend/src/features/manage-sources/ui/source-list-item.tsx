import { useCallback, useId, useState } from "react";
import type { VacancySource } from "@/entities/vacancy-source";
import { Button, VISUALLY_HIDDEN_STYLE, colors } from "@/shared/ui";
import {
  EDIT_LABEL,
  EDIT_UNAVAILABLE_HINT,
  SCANNING_LABEL,
  SOURCE_KIND_LABELS,
  UNAVAILABLE_FALLBACK_REASON,
  UNAVAILABLE_LABEL,
} from "../lib/constants";
import { getCheckedLabel, getPendingLabel } from "../lib/helpers";
import type { SourceSavedHandler } from "../model/types";
import { EditSourceDialog } from "./edit-source-dialog";

/** Looks like the Button's disabled state; the button itself stays focusable. */
const BLOCKED_BUTTON_STYLE = { opacity: 0.6, cursor: "not-allowed" } as const;

interface SourceListItemProps {
  source: VacancySource;
  isRemoving: boolean;
  onRemove: (id: string) => void;
  /** Called with this row's id and the server's copy (a new id after a replace). */
  onEdited: SourceSavedHandler;
  /** Called with the Remove button element (null on unmount) for focus management. */
  onRegisterRemoveButton: (id: string, element: HTMLButtonElement | null) => void;
  /** Called with the Edit button element (null on unmount) for focus management. */
  onRegisterEditButton: (id: string, element: HTMLButtonElement | null) => void;
}

/**
 * One watched source: name, kind, scan/last-checked/availability status,
 * "Waiting for AI: N" when posts of it wait to be rated, an
 * Edit button (opens `EditSourceDialog`; the Modal returns focus to it on close;
 * `aria-disabled` with a described reason while a first-scan attempt runs,
 * `editable: false`) and a Remove button.
 */
export function SourceListItem({
  source,
  isRemoving,
  onRemove,
  onEdited,
  onRegisterRemoveButton,
  onRegisterEditButton,
}: SourceListItemProps) {
  const [isEditing, setIsEditing] = useState(false);
  const editHintId = useId();
  const { id, unavailable } = source;
  const checkedLabel = source.scanning ? null : getCheckedLabel(source);
  const pendingLabel = getPendingLabel(source.pending_count);
  const removeButtonRef = useCallback(
    (element: HTMLButtonElement | null) => onRegisterRemoveButton(id, element),
    [id, onRegisterRemoveButton],
  );
  const editButtonRef = useCallback(
    (element: HTMLButtonElement | null) => onRegisterEditButton(id, element),
    [id, onRegisterEditButton],
  );
  const isEditBlocked = !source.editable;
  const handleEditClick = useCallback((): void => {
    if (!isEditBlocked) setIsEditing(true);
  }, [isEditBlocked]);
  const closeEdit = useCallback(() => setIsEditing(false), []);
  const handleSaved = useCallback(
    (updated: VacancySource): void => {
      setIsEditing(false);
      onEdited(id, updated);
    },
    [id, onEdited],
  );

  return (
    <li
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.75rem",
        padding: unavailable ? "0.625rem 0.5rem" : "0.625rem 0",
        borderBottom: `1px solid ${colors.borderLight}`,
        borderLeft: unavailable ? `3px solid ${colors.badge.danger.text}` : undefined,
        backgroundColor: unavailable ? colors.badge.danger.bg : undefined,
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <p
          style={{
            fontSize: "0.875rem",
            fontWeight: 500,
            color: colors.textPrimary,
            overflowWrap: "anywhere",
          }}
        >
          {source.display_name}
        </p>
        {/* textMuted is 3.96:1 on the danger tint; textSecondary keeps AA on it */}
        <p style={{ fontSize: "0.75rem", color: unavailable ? colors.textSecondary : colors.textMuted }}>
          {SOURCE_KIND_LABELS[source.kind]}
          {source.scanning ? ` · ${SCANNING_LABEL}` : null}
          {checkedLabel ? ` · ${checkedLabel}` : null}
        </p>
        {pendingLabel ? (
          <p style={{ fontSize: "0.75rem", color: unavailable ? colors.textSecondary : colors.textMuted }}>
            {pendingLabel}
          </p>
        ) : null}
        {/* Plain text in reading order: name, kind, then "Unavailable — reason" */}
        {unavailable ? (
          <p style={{ fontSize: "0.75rem", fontWeight: 600, color: colors.badge.danger.text }}>
            {`${UNAVAILABLE_LABEL} — ${source.last_error || UNAVAILABLE_FALLBACK_REASON}`}
          </p>
        ) : null}
      </div>
      <Button
        ref={editButtonRef}
        type="button"
        variant="secondary"
        aria-label={`${EDIT_LABEL} ${source.display_name}`}
        // aria-disabled (not disabled) keeps it focusable so the reason is
        // announced; re-enabled by a poll once the scan attempt ends
        aria-disabled={isEditBlocked || undefined}
        title={isEditBlocked ? EDIT_UNAVAILABLE_HINT : undefined}
        aria-describedby={isEditBlocked ? editHintId : undefined}
        onClick={handleEditClick}
        style={{ flexShrink: 0, ...(isEditBlocked ? BLOCKED_BUTTON_STYLE : null) }}
      >
        {EDIT_LABEL}
      </Button>
      {isEditBlocked ? (
        <span id={editHintId} style={VISUALLY_HIDDEN_STYLE}>
          {EDIT_UNAVAILABLE_HINT}
        </span>
      ) : null}
      <Button
        ref={removeButtonRef}
        type="button"
        variant="secondary"
        aria-label={`Remove ${source.display_name}`}
        loading={isRemoving}
        onClick={() => onRemove(source.id)}
        style={{ flexShrink: 0 }}
      >
        Remove
      </Button>
      {isEditing ? <EditSourceDialog source={source} onClose={closeEdit} onSaved={handleSaved} /> : null}
    </li>
  );
}
