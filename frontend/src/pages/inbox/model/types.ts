import type { Vacancy } from "@/entities/vacancy";

export type VacancyListLoadState = "loading" | "error" | "ready";

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
}
