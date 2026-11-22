import { useCallback } from "react";
import type { VacancySource } from "@/entities/vacancy-source";
import { Button, colors } from "@/shared/ui";
import { formatTimeAgo } from "@/shared/lib";
import {
  LAST_CHECKED_PREFIX,
  SCANNING_LABEL,
  SOURCE_KIND_LABELS,
  UNAVAILABLE_FALLBACK_REASON,
  UNAVAILABLE_LABEL,
} from "../lib/constants";

interface SourceListItemProps {
  source: VacancySource;
  isRemoving: boolean;
  onRemove: (id: string) => void;
  /** Called with the Remove button element (null on unmount) for focus management. */
  onRegisterRemoveButton: (id: string, element: HTMLButtonElement | null) => void;
}

/** One watched source: name, kind, scan/last-checked/availability status and a Remove button. */
export function SourceListItem({
  source,
  isRemoving,
  onRemove,
  onRegisterRemoveButton,
}: SourceListItemProps) {
  const { id, unavailable } = source;
  const removeButtonRef = useCallback(
    (element: HTMLButtonElement | null) => onRegisterRemoveButton(id, element),
    [id, onRegisterRemoveButton],
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
          {!source.scanning && source.last_checked_at
            ? ` · ${LAST_CHECKED_PREFIX} ${formatTimeAgo(source.last_checked_at)}`
            : null}
        </p>
        {/* Plain text in reading order: name, kind, then "Unavailable — reason" */}
        {unavailable ? (
          <p style={{ fontSize: "0.75rem", fontWeight: 600, color: colors.badge.danger.text }}>
            {`${UNAVAILABLE_LABEL} — ${source.last_error || UNAVAILABLE_FALLBACK_REASON}`}
          </p>
        ) : null}
      </div>
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
    </li>
  );
}
