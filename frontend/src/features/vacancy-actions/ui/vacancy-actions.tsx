import { memo, useCallback } from "react";
import { Button } from "@/shared/ui";
import type { Vacancy } from "@/entities/vacancy";
import { DISMISS_LABEL, OPEN_SOURCE_LABEL, UNSAFE_URL_HINT } from "../lib/constants";
import { isSafeExternalUrl } from "../lib/helpers";

interface VacancyActionsProps {
  vacancy: Vacancy;
  onOpenSource: (vacancy: Vacancy) => void;
  onDismiss: (vacancy: Vacancy) => void;
  /** Receives the Dismiss button (null on unmount), so the list can move focus after a dismiss. */
  onRegisterDismissButton?: (id: string, element: HTMLButtonElement | null) => void;
}

/** "Open source" and "Dismiss" buttons for a card's `actions` slot. */
export const VacancyActions = memo(function VacancyActions({
  vacancy,
  onOpenSource,
  onDismiss,
  onRegisterDismissButton,
}: VacancyActionsProps) {
  const { id } = vacancy;
  const dismissRef = useCallback(
    (element: HTMLButtonElement | null) => onRegisterDismissButton?.(id, element),
    [id, onRegisterDismissButton],
  );
  const isUrlSafe = isSafeExternalUrl(vacancy.url);

  return (
    <>
      <Button
        type="button"
        disabled={!isUrlSafe}
        title={isUrlSafe ? undefined : UNSAFE_URL_HINT}
        onClick={() => onOpenSource(vacancy)}
      >
        {OPEN_SOURCE_LABEL}
      </Button>
      <Button
        ref={dismissRef}
        type="button"
        variant="secondary"
        onClick={() => onDismiss(vacancy)}
      >
        {DISMISS_LABEL}
      </Button>
    </>
  );
});
