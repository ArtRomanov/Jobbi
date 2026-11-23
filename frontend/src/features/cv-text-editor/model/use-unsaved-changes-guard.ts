import { useCallback, useEffect, useLayoutEffect, useRef } from "react";
import { useBlocker, type BlockerFunction } from "react-router-dom";

export interface UnsavedChangesGuard {
  /** True while an in-app navigation waits for the user's "Leave" / "Stay". */
  isPrompting: boolean;
  /** Carry on with the blocked navigation (the draft is dropped). */
  leave: () => void;
  /** Cancel the blocked navigation and stay on the page. */
  stay: () => void;
}

/**
 * Guards unsaved changes while `isDirty`:
 * - in-app navigation (link click, Back/Forward) is held by `useBlocker` until
 *   the caller's dialog calls `leave` or `stay`;
 * - closing or reloading the tab gets the browser's own leave prompt
 *   (`beforeunload`; browsers ignore any custom text there).
 *
 * `REPLACE` navigations are not blocked: they are the page swapping its own
 * URL (e.g. `/cvs/new` → `/cvs/<id>/edit` right after the first save, before
 * the saved values reach this hook), not the user leaving.
 */
export function useUnsavedChangesGuard(isDirty: boolean): UnsavedChangesGuard {
  // Read at navigation time, so the blocker function never goes stale
  const isDirtyRef = useRef(isDirty);
  useLayoutEffect(() => {
    isDirtyRef.current = isDirty;
  }, [isDirty]);

  const shouldBlock = useCallback<BlockerFunction>(
    ({ currentLocation, nextLocation, historyAction }) =>
      isDirtyRef.current &&
      historyAction !== "REPLACE" &&
      (currentLocation.pathname !== nextLocation.pathname ||
        currentLocation.search !== nextLocation.search),
    [],
  );
  const blocker = useBlocker(shouldBlock);

  useEffect(() => {
    if (!isDirty) return;
    function handleBeforeUnload(event: BeforeUnloadEvent): void {
      event.preventDefault();
      // Older browsers show the prompt only when returnValue is set
      event.returnValue = "";
    }
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isDirty]);

  const { proceed, reset } = blocker;
  const leave = useCallback(() => proceed?.(), [proceed]);
  const stay = useCallback(() => reset?.(), [reset]);

  return { isPrompting: blocker.state === "blocked", leave, stay };
}
