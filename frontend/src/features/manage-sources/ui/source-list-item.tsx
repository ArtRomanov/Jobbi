import { useCallback, useState } from "react";
import type { VacancySource } from "@/entities/vacancy-source";
import { Button, colors } from "@/shared/ui";
import {
  EDIT_LABEL,
  SCANNING_LABEL,
  SOURCE_KIND_LABELS,
  UNAVAILABLE_FALLBACK_REASON,
  UNAVAILABLE_LABEL,
} from "../lib/constants";
import { getCheckedLabel } from "../lib/helpers";
import type { SourceEditedHandler } from "../model/types";
import { EditSourceDialog } from "./edit-source-dialog";

interface SourceListItemProps {
  source: VacancySource;
  isRemoving: boolean;
  onRemove: (id: string) => void;
  /** Called with the server's copy after a successful edit. */
  onEdited: SourceEditedHandler;
  /** Called with the Remove button element (null on unmount) for focus management. */
  onRegisterRemoveButton: (id: string, element: HTMLButtonElement | null) => void;
}

/**
 * One watched source: name, kind, scan/last-checked/availability status, an
 * Edit button (opens `EditSourceDialog`; the Modal returns focus to it on close)
 * and a Remove button.
 */
export function SourceListItem({
  source,
  isRemoving,
  onRemove,
  onEdited,
  onRegisterRemoveButton,
}: SourceListItemProps) {
  const [isEditing, setIsEditing] = useState(false);
  const { id, unavailable } = source;
  const checkedLabel = source.scanning ? null : getCheckedLabel(source);
  const removeButtonRef = useCallback(
    (element: HTMLButtonElement | null) => onRegisterRemoveButton(id, element),
    [id, onRegisterRemoveButton],
  );
  const closeEdit = useCallback(() => setIsEditing(false), []);
  const handleSaved = useCallback(
    (updated: VacancySource): void => {
      setIsEditing(false);
      onEdited(updated);
    },
    [onEdited],
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
        {/* Plain text in reading order: name, kind, then "Unavailable — reason" */}
        {unavailable ? (
          <p style={{ fontSize: "0.75rem", fontWeight: 600, color: colors.badge.danger.text }}>
            {`${UNAVAILABLE_LABEL} — ${source.last_error || UNAVAILABLE_FALLBACK_REASON}`}
          </p>
        ) : null}
      </div>
      <Button
        type="button"
        variant="secondary"
        aria-label={`${EDIT_LABEL} ${source.display_name}`}
        onClick={() => setIsEditing(true)}
        style={{ flexShrink: 0 }}
      >
        {EDIT_LABEL}
      </Button>
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
