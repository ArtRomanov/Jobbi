import { useCallback, useId } from "react";
import { usePersistentBoolean } from "./use-persistent-boolean";

interface CollapsibleSectionOptions {
  /** Open on this mount even if the saved choice is collapsed (not saved). */
  forceExpanded?: boolean;
}

export interface CollapsibleSection {
  isExpanded: boolean;
  toggle: () => void;
  /** Id for the collapsible region (the toggle's `aria-controls`). */
  regionId: string;
}

/**
 * Show/hide state for a page section, remembered per browser under
 * `storageKey` (stores "true" when collapsed). Default: expanded.
 */
export function useCollapsibleSection(
  storageKey: string,
  { forceExpanded = false }: CollapsibleSectionOptions = {},
): CollapsibleSection {
  const regionId = useId();
  const [isCollapsed, setCollapsed] = usePersistentBoolean(storageKey, false, {
    initialValue: forceExpanded ? false : undefined,
  });
  const toggle = useCallback(() => setCollapsed(!isCollapsed), [isCollapsed, setCollapsed]);
  return { isExpanded: !isCollapsed, toggle, regionId };
}
