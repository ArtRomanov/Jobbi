import type { Vacancy } from "@/entities/vacancy";

export type VacancyListLoadState = "loading" | "error" | "ready";

export interface VacancyListState {
  items: readonly Vacancy[];
  /** Server total for the current filters, adjusted by local removes/restores. */
  total: number;
}

export interface UseVacancyListResult {
  items: readonly Vacancy[];
  total: number;
  loadState: VacancyListLoadState;
  hasMore: boolean;
  isLoadingMore: boolean;
  /** Inline error under "Load more", or null. */
  loadMoreError: string | null;
  loadMore: () => Promise<void>;
  retry: () => void;
  /** Replace a card in place (same id). */
  updateItem: (vacancy: Vacancy) => void;
  /** Take a card out; its position is remembered for `restoreItem`. */
  removeItem: (id: string) => void;
  /**
   * Put a removed card back where it was. No-op if it is already listed, if a
   * page-1 load since the remove no longer lists it, or if its state does not
   * match the current state filter.
   */
  restoreItem: (vacancy: Vacancy) => void;
}
