import { useCallback, useRef, useState } from "react";
import { getErrorMessage } from "@/shared/api";
import { addVacancySource, previewVacancySource } from "@/entities/vacancy-source";
import type { VacancySource } from "@/entities/vacancy-source";
import type { WebSourceOptions } from "./schemas";
import type { AddSourceAction, AddSubmitOutcome, UseAddSourceResult, WebPreview } from "./types";

/**
 * The add flow: Add → preview. A non-web kind is created right away (today's
 * flow); a web page opens an inline preview that can be re-checked with a
 * "Job link contains" pattern and is only saved on Save.
 *
 * One ref blocks every overlapping request (submit, re-check, save), so a
 * second Enter before React re-renders cannot send a duplicate.
 *
 * `beforeAdd` runs (awaited) before Add / Save / "Add the board" talk to the
 * server: the panel sends pending removals there, so re-adding a source whose
 * Undo window is still open is not a duplicate and a hidden row does not
 * count toward the source limit.
 */
export function useAddSource(
  isDisabled: boolean,
  onAdded: (source: VacancySource) => void,
  beforeAdd?: () => Promise<void>,
): UseAddSourceResult {
  const [input, setInputValue] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<AddSourceAction | null>(null);
  const [preview, setPreview] = useState<WebPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const busyRef = useRef(false);

  /** Runs `task` unless another request is in flight; false when skipped. */
  const runExclusive = useCallback(
    async (action: AddSourceAction, task: () => Promise<void>): Promise<boolean> => {
      if (busyRef.current) return false;
      busyRef.current = true;
      setBusyAction(action);
      try {
        await task();
      } finally {
        busyRef.current = false;
        setBusyAction(null);
      }
      return true;
    },
    [],
  );

  // Editing the link makes an open preview stale, so it closes
  const setInput = useCallback((value: string): void => {
    setInputValue(value);
    setAddError(null);
    setPreview(null);
    setPreviewError(null);
  }, []);

  const submit = useCallback(async (): Promise<AddSubmitOutcome> => {
    const value = input.trim();
    if (value === "" || isDisabled) return "skipped";
    let outcome: AddSubmitOutcome = "skipped";
    await runExclusive("submit", async () => {
      setAddError(null);
      setPreviewError(null);
      try {
        await beforeAdd?.();
        const result = await previewVacancySource({ input: value });
        if (result.kind === "web") {
          setPreview((prev) => ({ id: (prev?.id ?? 0) + 1, input: value, result }));
          outcome = "preview";
          return;
        }
        setPreview(null);
        const created = await addVacancySource({ input: value });
        onAdded(created);
        setInputValue("");
        outcome = "added";
      } catch (error: unknown) {
        setPreview(null);
        setAddError(getErrorMessage(error));
        outcome = "error";
      }
    });
    return outcome;
  }, [input, isDisabled, onAdded, beforeAdd, runExclusive]);

  const recheck = useCallback(
    async (jobLinkContains: string | null): Promise<void> => {
      const current = preview;
      if (current === null) return;
      await runExclusive("recheck", async () => {
        setPreviewError(null);
        try {
          const result = await previewVacancySource({
            input: current.input,
            job_link_contains: jobLinkContains,
          });
          // Same preview id: the form keeps the user's drafts
          setPreview((prev) => (prev?.id === current.id ? { ...prev, result } : prev));
        } catch (error: unknown) {
          setPreviewError(getErrorMessage(error));
        }
      });
    },
    [preview, runExclusive],
  );

  const save = useCallback(
    async (options: WebSourceOptions): Promise<boolean> => {
      const current = preview;
      if (current === null) return false;
      let isSaved = false;
      await runExclusive("save", async () => {
        setPreviewError(null);
        try {
          await beforeAdd?.();
          const created = await addVacancySource({
            input: current.input,
            job_link_contains: options.jobLinkContains,
            name: options.name,
          });
          onAdded(created);
          setInputValue("");
          setPreview(null);
          isSaved = true;
        } catch (error: unknown) {
          setPreviewError(getErrorMessage(error));
        }
      });
      return isSaved;
    },
    [preview, onAdded, beforeAdd, runExclusive],
  );

  // The ATS hint's board goes the non-web way (like a pasted board link);
  // errors stay inside the preview, success closes it and clears the input
  const addBoard = useCallback(
    async (boardInput: string): Promise<boolean> => {
      let isAdded = false;
      await runExclusive("board", async () => {
        setPreviewError(null);
        try {
          await beforeAdd?.();
          const created = await addVacancySource({ input: boardInput });
          onAdded(created);
          setInputValue("");
          setPreview(null);
          isAdded = true;
        } catch (error: unknown) {
          setPreviewError(getErrorMessage(error));
        }
      });
      return isAdded;
    },
    [onAdded, beforeAdd, runExclusive],
  );

  const cancelPreview = useCallback((): void => {
    if (busyRef.current) return;
    setPreview(null);
    setPreviewError(null);
  }, []);

  return {
    input,
    setInput,
    addError,
    busyAction,
    isBusy: busyAction !== null,
    preview,
    previewError,
    submit,
    recheck,
    save,
    addBoard,
    cancelPreview,
  };
}
