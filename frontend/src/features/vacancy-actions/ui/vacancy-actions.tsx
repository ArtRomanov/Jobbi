import { memo, useCallback, useState } from "react";
import { Button } from "@/shared/ui";
import { isSafeExternalUrl } from "@/shared/lib";
import { getVacancyLabel } from "@/entities/vacancy";
import type { Vacancy } from "@/entities/vacancy";
import {
  ADD_TO_TRACKER_LABEL,
  DISMISS_LABEL,
  OPEN_SOURCE_LABEL,
  UNSAFE_URL_HINT,
} from "../lib/constants";
import { AddToTrackerDialog } from "./add-to-tracker-dialog";

interface VacancyActionsProps {
  vacancy: Vacancy;
  onOpenSource: (vacancy: Vacancy) => void;
  onDismiss: (vacancy: Vacancy) => void;
  /** Opening the dialog marks the card seen (spec 2.3). */
  onMarkSeen: (vacancy: Vacancy) => void;
  /** The card was added to the tracker: take it out of the list. */
  onAdded: (vacancy: Vacancy) => void;
  /** Receives the Dismiss button (null on unmount), so the list can move focus after a dismiss. */
  onRegisterDismissButton?: (id: string, element: HTMLButtonElement | null) => void;
}

/** "Open source", "Add to tracker" (opens its dialog) and "Dismiss" for a card's `actions` slot. */
export const VacancyActions = memo(function VacancyActions({
  vacancy,
  onOpenSource,
  onDismiss,
  onMarkSeen,
  onAdded,
  onRegisterDismissButton,
}: VacancyActionsProps) {
  const { id } = vacancy;
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const dismissRef = useCallback(
    (element: HTMLButtonElement | null) => onRegisterDismissButton?.(id, element),
    [id, onRegisterDismissButton],
  );
  const closeAddDialog = useCallback(() => setIsAddDialogOpen(false), []);
  const handleAdded = useCallback(
    (added: Vacancy) => {
      setIsAddDialogOpen(false);
      onAdded(added);
    },
    [onAdded],
  );
  const isUrlSafe = isSafeExternalUrl(vacancy.url);
  // Distinct names per card: a screen reader's button list would otherwise read "Dismiss" ×N
  const vacancyLabel = getVacancyLabel(vacancy);

  return (
    <>
      <Button
        type="button"
        disabled={!isUrlSafe}
        title={isUrlSafe ? undefined : UNSAFE_URL_HINT}
        aria-label={`${OPEN_SOURCE_LABEL} for ${vacancyLabel}`}
        onClick={() => onOpenSource(vacancy)}
      >
        {OPEN_SOURCE_LABEL}
      </Button>
      <Button
        type="button"
        variant="secondary"
        aria-haspopup="dialog"
        aria-label={`${ADD_TO_TRACKER_LABEL}: ${vacancyLabel}`}
        onClick={() => {
          setIsAddDialogOpen(true);
          // Spec 2.3: clicking "Add to tracker" makes a new card seen (no-op if already seen)
          onMarkSeen(vacancy);
        }}
      >
        {ADD_TO_TRACKER_LABEL}
      </Button>
      <Button
        ref={dismissRef}
        type="button"
        variant="secondary"
        aria-label={`${DISMISS_LABEL} ${vacancyLabel}`}
        onClick={() => onDismiss(vacancy)}
      >
        {DISMISS_LABEL}
      </Button>
      {isAddDialogOpen ? (
        <AddToTrackerDialog
          vacancy={vacancy}
          onClose={closeAddDialog}
          onAdded={handleAdded}
          onMarkSeen={onMarkSeen}
        />
      ) : null}
    </>
  );
});
