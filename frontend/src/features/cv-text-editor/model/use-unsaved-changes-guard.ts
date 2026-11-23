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
 * Why `REPLACE` navigations are never blocked: users leave through PUSH (a
 * link or nav click) or POP (Back/Forward); a REPLACE is the app rewriting its
 * own history entry. The CV editor does that twice, and blocking either would
 * prompt for a navigation the user never made:
 * - after the first save, `/cvs/new` → `/cvs/<id>/edit`. The navigate call runs
 *   in the save handler before the saved values re-render into this hook, so
 *   `isDirty` is still true at that moment;
 * - `useUploadDraft` (`features/cv-upload`) clears the upload draft's router
 *   state with a same-URL replace right after `/cvs/new` opens it, while the
 *   draft is already dirty (also skipped by the pathname/search check below).
 * Accepted trade-off: other app replaces (e.g. the auth redirect to `/login`)
 * are not guarded either.
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
