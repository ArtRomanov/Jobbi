import { useEffect, useRef } from "react";
import { Button, colors } from "@/shared/ui";
import type { ExistingApplicationRef } from "@/entities/vacancy";
import { ADD_ANYWAY_LABEL, DUPLICATE_PREFIX, OPEN_EXISTING_LABEL } from "../lib/constants";

interface DuplicateWarningProps {
  application: ExistingApplicationRef;
  /** Id of the warning sentence, for the dialog's `aria-describedby`. */
  textId: string;
  /** A change (> 0) moves focus to "Add anyway": the user must answer the warning. */
  attention: number;
  isDisabled: boolean;
  onOpenExisting: () => void;
  onAddAnyway: () => void;
}

/** "You already track this: <Company> — <Role>" with "Open it" / "Add anyway". */
export function DuplicateWarning({
  application,
  textId,
  attention,
  isDisabled,
  onOpenExisting,
  onAddAnyway,
}: DuplicateWarningProps) {
  const addAnywayRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (attention > 0) addAnywayRef.current?.focus();
  }, [attention]);

  return (
    <div
      role="alert"
      style={{
        marginBottom: "1rem",
        padding: "0.75rem",
        borderRadius: "0.375rem",
        backgroundColor: colors.badge.warning.bg,
        color: colors.badge.warning.text,
        fontSize: "0.875rem",
      }}
    >
      <p id={textId} style={{ margin: "0 0 0.5rem" }}>
        {DUPLICATE_PREFIX} {application.company_name} — {application.role_title}
      </p>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <Button type="button" variant="secondary" disabled={isDisabled} onClick={onOpenExisting}>
          {OPEN_EXISTING_LABEL}
        </Button>
        <Button
          ref={addAnywayRef}
          type="button"
          variant="secondary"
          disabled={isDisabled}
          onClick={onAddAnyway}
        >
          {ADD_ANYWAY_LABEL}
        </Button>
      </div>
    </div>
  );
}
