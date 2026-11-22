import type { Vacancy, VacancyListParams } from "@/entities/vacancy";
import type { InboxFilterValues, InboxStateFilter } from "@/features/inbox-filters";
import { VACANCIES_PER_PAGE } from "./constants";

/** Query for one page of the list under the given filters. */
export function buildListParams(filters: InboxFilterValues, page: number): VacancyListParams {
  return {
    source: filters.source ?? undefined,
    state: filters.state,
    sort: filters.sort,
    page,
    per_page: VACANCIES_PER_PAGE,
  };
}

/**
 * Card to focus after removing `id`: the one that moves into its place, else
 * the one before it, else null (the list is now empty).
 */
export function pickFocusAfterRemove(ids: readonly string[], id: string): string | null {
  const index = ids.indexOf(id);
  if (index === -1) return null;
  return ids[index + 1] ?? ids[index - 1] ?? null;
}

/** Copy of `items` with `item` at `index` (clamped to the end). */
export function insertAt<T>(items: readonly T[], index: number, item: T): T[] {
  const position = Math.min(Math.max(index, 0), items.length);
  return [...items.slice(0, position), item, ...items.slice(position)];
}

/** Whether a card in `vacancyState` belongs in a list filtered by `filter`. */
export function matchesStateFilter(vacancyState: Vacancy["state"], filter: InboxStateFilter): boolean {
  if (filter === "all") return vacancyState === "new" || vacancyState === "seen";
  return vacancyState === filter;
}
