import type { Cv } from "@/entities/cv";
import type { ExistingApplicationRef, Vacancy } from "@/entities/vacancy";
import type { AddToTrackerFormValues } from "./schemas";

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
  /** new → seen (optimistic; reverted if the request fails). No-op for a seen card. */
  markSeen: (vacancy: Vacancy) => void;
  /** After a successful add: takes the card out of the list. */
  completeAdd: (vacancy: Vacancy) => void;
}

/** Which dialog button submitted: plain add, or add + CV copy + chat. */
export type AddMode = "plain" | "tailor";

export type BaseCvsStatus = "loading" | "ready" | "error";

export interface BaseCvsResult {
  cvs: readonly Cv[];
  status: BaseCvsStatus;
  /** The base CV (preselected), or null when the user has none (nothing preselected). */
  defaultCvId: string | null;
}

export interface AddToTrackerCallbacks {
  /** Closes the dialog (Cancel, Escape, "Open it"). */
  onClose: () => void;
  /** The application was created: the list drops the card. */
  onAdded: (vacancy: Vacancy) => void;
  /** "Open it" marks the card seen (it stays in the Inbox). */
  onMarkSeen: (vacancy: Vacancy) => void;
}

export interface UseAddToTrackerResult {
  isSubmitting: boolean;
  /** Inline error, or null. */
  error: string | null;
  /** Application already tracking this link (from the card or a 409), or null. */
  duplicate: ExistingApplicationRef | null;
  /** Grows each time the user must answer the duplicate warning (focus "Add anyway"). */
  duplicateAttention: number;
  /** Sends nothing while the duplicate warning shows (asks for "Add anyway" instead). */
  submit: (values: AddToTrackerFormValues, mode: AddMode) => Promise<void>;
  /** "Add anyway": the last pressed add button's mode (plain if none) with `allow_duplicate`. */
  submitAnyway: (values: AddToTrackerFormValues) => Promise<void>;
  /** "Open it": marks the card seen, closes the dialog, opens the application on the dashboard. */
  openExisting: () => void;
}
