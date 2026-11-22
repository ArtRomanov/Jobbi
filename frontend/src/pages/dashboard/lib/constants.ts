import type { SegmentedControlOption } from "@/shared/ui";
import type { DashboardTab } from "../model/types";

/** Debounce delay for the search input (milliseconds). */
export const SEARCH_DEBOUNCE_MS = 300;

/** Options of the Board / Timeline view toggle. */
export const DASHBOARD_VIEW_OPTIONS: readonly SegmentedControlOption<DashboardTab>[] = [
  { value: "board", label: "Board" },
  { value: "timeline", label: "Timeline" },
];
