import type { SegmentedControlOption } from "@/shared/ui";
import type { InboxFilterValues, InboxSort, InboxStateFilter } from "../model/types";

export const DEFAULT_INBOX_FILTERS: InboxFilterValues = {
  source: null,
  state: "all",
  sort: "date",
};

/** `<select>` value of "All sources" (a source key is never empty). */
export const ALL_SOURCES_VALUE = "";
export const ALL_SOURCES_LABEL = "All sources";
export const REMOVED_SOURCE_SUFFIX = " (removed)";
/** Channels the user forwarded posts from (not watched, so never "removed"). */
export const FORWARDED_SOURCE_SUFFIX = " (forwarded)";
/** Source-key prefix of posts forwarded to the bot (backend `FORWARDED_KIND`). */
export const FORWARDED_SOURCE_KEY_PREFIX = "tg_forward:";

export const STATE_OPTIONS: readonly SegmentedControlOption<InboxStateFilter>[] = [
  { value: "new", label: "New" },
  { value: "seen", label: "Seen" },
  { value: "all", label: "All" },
];

export const SORT_OPTIONS: readonly SegmentedControlOption<InboxSort>[] = [
  { value: "date", label: "Newest" },
  { value: "fit", label: "Best fit" },
];
