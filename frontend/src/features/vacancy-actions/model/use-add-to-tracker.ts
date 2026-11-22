import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ROUTES } from "@/shared/config";
import { useToast } from "@/shared/ui";
import {
  addVacancyToTracker,
  getDuplicateApplication,
  notifyVacanciesChanged,
} from "@/entities/vacancy";
import type { ExistingApplicationRef, Vacancy } from "@/entities/vacancy";
import type { ChatRouteState } from "@/entities/chat";
import {
  ADDED_MESSAGE,
  ADDED_TOAST_DURATION_MS,
  ALREADY_ADDED_MESSAGE,
  OPEN_APPLICATION_LABEL,
  TAILOR_CV_DRAFT,
} from "../lib/constants";
import { getAddErrorMessage, isAlreadyAddedError, toAddToTrackerBody } from "../lib/helpers";
import type { AddToTrackerFormValues } from "./schemas";
import type { AddMode, AddToTrackerCallbacks, UseAddToTrackerResult } from "./types";

/**
 * Submit logic of the "Add to tracker" dialog. One request at a time (a ref
 * guards double clicks before the re-render disables the buttons).
 *
 * - While the duplicate warning shows, the two add buttons send nothing (the
 *   server would answer 409): they only remember the mode and ask for "Add
 *   anyway", which sends that mode with `allow_duplicate`.
 * - Success: badge refresh, `onAdded` (card leaves the list), then a toast
 *   linking to the application (plain) or the chat with an unsent draft (tailor).
 * - Structured 409 → duplicate warning; 409 "Already added" → card leaves with
 *   an info toast; anything else → inline error.
 */
export function useAddToTracker(
  vacancy: Vacancy,
  callbacks: AddToTrackerCallbacks,
): UseAddToTrackerResult {
  const { showToast } = useToast();
  const navigate = useNavigate();
  const callbacksRef = useRef(callbacks);
  useEffect(() => {
    callbacksRef.current = callbacks;
  });
  const isMountedRef = useRef(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState<ExistingApplicationRef | null>(
    () => vacancy.existing_application ?? null,
  );
  // Bumped whenever the user must answer the warning; the UI moves focus to "Add anyway"
  const [duplicateAttention, setDuplicateAttention] = useState(0);
  const isSubmittingRef = useRef(false);
  // The add button the user pressed last; "Add anyway" repeats it
  const lastModeRef = useRef<AddMode>("plain");

  const send = useCallback(
    async (values: AddToTrackerFormValues, mode: AddMode, allowDuplicate: boolean): Promise<void> => {
      if (isSubmittingRef.current) return;
      isSubmittingRef.current = true;
      setIsSubmitting(true);
      setError(null);
      try {
        const { application_id: applicationId } = await addVacancyToTracker(
          vacancy.id,
          toAddToTrackerBody(values, mode, allowDuplicate),
        );
        notifyVacanciesChanged();
        // Unmounts the dialog along with the card
        callbacksRef.current.onAdded(vacancy);
        if (mode === "tailor") {
          const state: ChatRouteState = { draft: TAILOR_CV_DRAFT };
          navigate(ROUTES.chat(applicationId), { state });
        } else {
          showToast(ADDED_MESSAGE, "success", {
            link: { label: OPEN_APPLICATION_LABEL, to: ROUTES.dashboardApplication(applicationId) },
            durationMs: ADDED_TOAST_DURATION_MS,
          });
        }
      } catch (caught: unknown) {
        if (!isMountedRef.current) return;
        if (isAlreadyAddedError(caught)) {
          // Added meanwhile (another tab): the card is stale, not an error
          notifyVacanciesChanged();
          callbacksRef.current.onAdded(vacancy);
          showToast(ALREADY_ADDED_MESSAGE, "info");
          return;
        }
        const tracked = getDuplicateApplication(caught);
        if (tracked) {
          setDuplicate(tracked);
          setDuplicateAttention((count) => count + 1);
        } else {
          setError(getAddErrorMessage(caught));
        }
      } finally {
        isSubmittingRef.current = false;
        if (isMountedRef.current) setIsSubmitting(false);
      }
    },
    [vacancy, navigate, showToast],
  );

  const submit = useCallback(
    async (values: AddToTrackerFormValues, mode: AddMode): Promise<void> => {
      lastModeRef.current = mode;
      if (duplicate) {
        setDuplicateAttention((count) => count + 1);
        return;
      }
      await send(values, mode, false);
    },
    [duplicate, send],
  );

  const submitAnyway = useCallback(
    async (values: AddToTrackerFormValues): Promise<void> => {
      await send(values, lastModeRef.current, true);
      // Hidden only after a failed retry; on success the dialog is gone
      if (isMountedRef.current) setDuplicate(null);
    },
    [send],
  );

  const openExisting = useCallback((): void => {
    if (!duplicate) return;
    const { onClose, onMarkSeen } = callbacksRef.current;
    onClose();
    onMarkSeen(vacancy);
    navigate(ROUTES.dashboardApplication(duplicate.id));
  }, [duplicate, vacancy, navigate]);

  return {
    isSubmitting,
    error,
    duplicate,
    duplicateAttention,
    submit,
    submitAnyway,
    openExisting,
  };
}
