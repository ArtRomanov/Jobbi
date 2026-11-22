import type { VacancyListParams } from "@/entities/vacancy";

/** "new" | "seen" | "all" (all = new + seen). */
export type InboxStateFilter = NonNullable<VacancyListParams["state"]>;

/** "date" (newest first) | "fit" (High → Medium → Low, newest first within a fit). */
export type InboxSort = NonNullable<VacancyListParams["sort"]>;

/** The Inbox filter bar's value. Filters combine. */
export interface InboxFilterValues {
  /** Source key ("<kind>:<handle>"), or null for all sources. */
  source: string | null;
  state: InboxStateFilter;
  sort: InboxSort;
}

export interface SourceOption {
  value: string;
  label: string;
}
