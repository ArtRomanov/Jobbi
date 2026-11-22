import type { Vacancy } from "@/entities/vacancy";

/** How the owner of the card list applies the actions' local changes. */
export interface VacancyActionsCallbacks {
  /** Replace a card in place (e.g. new → seen after "Open source"). */
  onUpdate: (vacancy: Vacancy) => void;
  /** Take a card out of the list (optimistic dismiss). */
  onRemove: (id: string) => void;
  /** Put a card back (Undo, or a failed dismiss). */
  onRestore: (vacancy: Vacancy) => void;
}

export interface UseVacancyActionsResult {
  /** Opens the card's URL in a new tab and marks a new card seen. */
  openSource: (vacancy: Vacancy) => void;
  /** Removes the card at once and offers Undo for 5 s. */
  dismiss: (vacancy: Vacancy) => void;
}
