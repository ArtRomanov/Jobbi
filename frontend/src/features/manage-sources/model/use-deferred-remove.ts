import { useCallback, useEffect, useRef, useState } from "react";
import { useToast } from "@/shared/ui";
import { REMOVE_UNDO_WINDOW_MS, SOURCE_REMOVED_MESSAGE, UNDO_LABEL } from "../lib/constants";
import type { SendRemove, UseDeferredRemoveResult } from "./types";

interface PendingRemoval {
  toastId: number;
  onUndo?: () => void;
}

/**
 * Remove with Undo, done on the client: `scheduleRemove` hides the row at once
 * (`pendingIds`) and shows "Source removed · Undo". Nothing is sent until the
 * toast ends by its own timer (it pauses on hover / focus); then `sendRemove`
 * runs once and the row stays hidden until it settles. Undo just un-hides it.
 *
 * Pending removals are sent at once (toasts closed) by `flushRemovals`, on
 * `pagehide` (with `keepalive`, so the request outlives the tab) and on unmount.
 * Each removal has its own toast and timer.
 */
export function useDeferredRemove(sendRemove: SendRemove): UseDeferredRemoveResult {
  const { showToast, dismissToast } = useToast();
  const [pendingIds, setPendingIds] = useState<ReadonlySet<string>>(() => new Set());
  // Removals whose DELETE has not been sent yet
  const pendingRef = useRef(new Map<string, PendingRemoval>());
  const sendRemoveRef = useRef(sendRemove);
  useEffect(() => {
    sendRemoveRef.current = sendRemove;
  });

  const unhide = useCallback((id: string): void => {
    setPendingIds((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }, []);

  const commit = useCallback(
    async (id: string, keepalive: boolean): Promise<void> => {
      const pending = pendingRef.current.get(id);
      if (!pending) return;
      pendingRef.current.delete(id);
      dismissToast(pending.toastId);
      try {
        await sendRemoveRef.current(id, { keepalive });
      } finally {
        // Success already dropped the row; failure shows it again
        unhide(id);
      }
    },
    [dismissToast, unhide],
  );

  const flush = useCallback(
    async (keepalive: boolean): Promise<void> => {
      await Promise.all([...pendingRef.current.keys()].map((id) => commit(id, keepalive)));
    },
    [commit],
  );

  const flushRemovals = useCallback((): Promise<void> => flush(false), [flush]);

  const undo = useCallback(
    (id: string): void => {
      const pending = pendingRef.current.get(id);
      if (!pending) return;
      pendingRef.current.delete(id);
      unhide(id);
      pending.onUndo?.();
    },
    [unhide],
  );

  const scheduleRemove = useCallback(
    (id: string, onUndo?: () => void): void => {
      if (pendingRef.current.has(id)) return;
      setPendingIds((prev) => new Set(prev).add(id));
      const toastId = showToast(SOURCE_REMOVED_MESSAGE, "info", {
        durationMs: REMOVE_UNDO_WINDOW_MS,
        action: { label: UNDO_LABEL, onClick: () => undo(id) },
        onTimeout: () => void commit(id, false),
      });
      pendingRef.current.set(id, { toastId, onUndo });
    },
    [commit, showToast, undo],
  );

  // Closing / reloading the tab or leaving the Inbox ends the Undo window: send now.
  // `flush` is stable (toast callbacks are), so the cleanup only runs on unmount
  useEffect(() => {
    function handlePageHide(): void {
      void flush(true);
    }
    window.addEventListener("pagehide", handlePageHide);
    return () => {
      window.removeEventListener("pagehide", handlePageHide);
      void flush(true);
    };
  }, [flush]);

  return { pendingIds, scheduleRemove, flushRemovals };
}
