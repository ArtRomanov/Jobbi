import { useCallback, useEffect, useRef } from "react";
import { handleApiError } from "@/shared/api";
import { useToast } from "@/shared/ui";
import {
  dismissVacancy,
  markVacancySeen,
  notifyVacanciesChanged,
  restoreVacancy,
} from "@/entities/vacancy";
import type { Vacancy } from "@/entities/vacancy";
import {
  DISMISSED_MESSAGE,
  NEW_TAB_FEATURES,
  RESTORE_ERROR_MESSAGE,
  UNDO_LABEL,
  UNDO_WINDOW_MS,
} from "../lib/constants";
import { isSafeExternalUrl } from "../lib/helpers";
import type { UseVacancyActionsResult, VacancyActionsCallbacks } from "./types";

/**
 * Inbox card actions. Mount it once per list (not per card): a dismissed card
 * unmounts, but its Undo must outlive it. Unmounting the hook (leaving the
 * Inbox) closes every open Undo toast, so the dismiss stays.
 *
 * Every server change calls `notifyVacanciesChanged()` so the nav badge refetches.
 */
export function useVacancyActions(callbacks: VacancyActionsCallbacks): UseVacancyActionsResult {
  const { showToast, dismissToast } = useToast();
  // Latest callbacks, so the returned functions stay stable for memoized cards
  const callbacksRef = useRef(callbacks);
  useEffect(() => {
    callbacksRef.current = callbacks;
  });
  const isMountedRef = useRef(false);
  const undoToastIdsRef = useRef(new Set<number>());

  useEffect(() => {
    isMountedRef.current = true;
    const undoToastIds = undoToastIdsRef.current;
    return () => {
      isMountedRef.current = false;
      // Leaving the page ends the Undo window
      undoToastIds.forEach((id) => dismissToast(id));
      undoToastIds.clear();
    };
  }, [dismissToast]);

  const openSource = useCallback((vacancy: Vacancy): void => {
    if (!isSafeExternalUrl(vacancy.url)) return;
    // Synchronously inside the click, so popup blockers allow it
    window.open(vacancy.url, "_blank", NEW_TAB_FEATURES);
    if (vacancy.state !== "new") return;

    callbacksRef.current.onUpdate({ ...vacancy, state: "seen" });
    markVacancySeen(vacancy.id)
      .catch(() => {
        // The tab is open anyway; show the card as new again so it matches the server
        if (isMountedRef.current) callbacksRef.current.onUpdate(vacancy);
      })
      .finally(notifyVacanciesChanged);
  }, []);

  const undo = useCallback(
    async (vacancy: Vacancy, dismissRequest: Promise<boolean>): Promise<void> => {
      // Restore only after the dismiss landed, or the two requests could cross
      const isDismissed = await dismissRequest;
      if (!isDismissed) return;
      try {
        await restoreVacancy(vacancy.id);
        if (isMountedRef.current) callbacksRef.current.onRestore({ ...vacancy, state: "seen" });
      } catch (error: unknown) {
        handleApiError(error, showToast, { 404: RESTORE_ERROR_MESSAGE, 409: RESTORE_ERROR_MESSAGE });
      } finally {
        notifyVacanciesChanged();
      }
    },
    [showToast],
  );

  const dismiss = useCallback(
    (vacancy: Vacancy): void => {
      callbacksRef.current.onRemove(vacancy.id);
      const undoToastIds = undoToastIdsRef.current;
      let toastId: number | null = null;

      const dismissRequest = dismissVacancy(vacancy.id).then(
        () => true,
        (error: unknown) => {
          if (toastId !== null) {
            dismissToast(toastId);
            undoToastIds.delete(toastId);
          }
          if (isMountedRef.current) callbacksRef.current.onRestore(vacancy);
          handleApiError(error, showToast);
          return false;
        },
      );
      void dismissRequest.finally(notifyVacanciesChanged);

      const id = showToast(DISMISSED_MESSAGE, "info", {
        durationMs: UNDO_WINDOW_MS,
        action: {
          label: UNDO_LABEL,
          onClick: () => {
            undoToastIds.delete(id);
            void undo(vacancy, dismissRequest);
          },
        },
      });
      toastId = id;
      undoToastIds.add(id);
    },
    [dismissToast, showToast, undo],
  );

  return { openSource, dismiss };
}
