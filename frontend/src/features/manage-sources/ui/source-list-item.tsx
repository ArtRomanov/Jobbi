import { useCallback } from "react";
import type { VacancySource } from "@/entities/vacancy-source";
import { Button, colors } from "@/shared/ui";
import { SCANNING_LABEL, SOURCE_KIND_LABELS, UNAVAILABLE_LABEL } from "../lib/constants";

interface SourceListItemProps {
  source: VacancySource;
  isRemoving: boolean;
  onRemove: (id: string) => void;
  /** Called with the Remove button element (null on unmount) for focus management. */
  onRegisterRemoveButton: (id: string, element: HTMLButtonElement | null) => void;
}

/** One watched source: name, kind, scan/availability status and a Remove button. */
export function SourceListItem({
  source,
  isRemoving,
  onRemove,
  onRegisterRemoveButton,
}: SourceListItemProps) {
  const { id } = source;
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
        padding: "0.625rem 0",
        borderBottom: `1px solid ${colors.borderLight}`,
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
        <p style={{ fontSize: "0.75rem", color: colors.textMuted }}>
          {SOURCE_KIND_LABELS[source.kind]}
          {source.scanning ? ` · ${SCANNING_LABEL}` : null}
        </p>
        {source.unavailable ? (
          <p style={{ fontSize: "0.75rem", color: colors.error }}>
            {UNAVAILABLE_LABEL}
            {source.last_error ? ` — ${source.last_error}` : null}
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
