import { useCallback, useRef, useState } from "react";
import { getErrorMessage } from "@/shared/api";
import { previewVacancySource, updateVacancySource } from "@/entities/vacancy-source";
import type { VacancySource } from "@/entities/vacancy-source";
import { getSourceLink } from "../lib/helpers";
import type { EditSourceValues, WebSourceOptions } from "./schemas";
import type { EditPreview, EditSourceAction, EditSourceField, UseEditSourceResult } from "./types";

/**
 * Requests of the Edit dialog.
 *
 * - Name only (link and pattern unchanged) → PATCH `{name}`.
 * - Changed link / pattern → preview with `source_id` (the edited source is
 *   left out of duplicate and limit checks). A web page opens the preview
 *   (found N, titles, re-check) and is PATCHed on its Save; any other kind is
 *   PATCHed right away. For non-web kinds the server answers with a NEW source.
 *
 * `onSaved` gets the server's copy. One ref blocks overlapping requests.
 * `submit` resolves with the field to focus after an error (else null).
 */
export function useEditSource(
  source: VacancySource,
  onSaved: (source: VacancySource) => void,
  // A removal still in its Undo window would make the changed link a 409 duplicate
  beforeLinkChange?: () => Promise<void>,
): UseEditSourceResult {
  const [busyAction, setBusyAction] = useState<EditSourceAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<EditPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const busyRef = useRef(false);
  const { id: sourceId, kind } = source;
  // The dialog's starting values; edits are measured against these
  const initialLinkRef = useRef(getSourceLink(source));
  const initialPatternRef = useRef(source.job_link_contains);

  const runExclusive = useCallback(
    async (action: EditSourceAction, task: () => Promise<void>): Promise<void> => {
      if (busyRef.current) return;
      busyRef.current = true;
      setBusyAction(action);
      try {
        await task();
      } finally {
        busyRef.current = false;
        setBusyAction(null);
      }
    },
    [],
  );

  const submit = useCallback(
    async (values: EditSourceValues): Promise<EditSourceField | null> => {
      let isFailed = false;
      const isLinkChanged = values.link !== initialLinkRef.current;
      const isPatternChanged = kind === "web" && values.jobLinkContains !== initialPatternRef.current;
      await runExclusive("check", async () => {
        setError(null);
        try {
          if (!isLinkChanged && !isPatternChanged) {
            onSaved(await updateVacancySource(sourceId, { name: values.name }));
            return;
          }
          await beforeLinkChange?.();
          // The pattern field only exists for a web source
          const jobLinkContains = kind === "web" ? values.jobLinkContains : null;
          const result = await previewVacancySource({
            input: values.link,
            job_link_contains: jobLinkContains,
            source_id: sourceId,
          });
          if (result.kind === "web") {
            setPreviewError(null);
            setPreview((prev) => ({
              id: (prev?.id ?? 0) + 1,
              input: values.link,
              result,
              initialJobLinkContains: jobLinkContains ?? "",
              initialName: values.name ?? "",
            }));
            return;
          }
          onSaved(await updateVacancySource(sourceId, { input: values.link, name: values.name }));
        } catch (caught: unknown) {
          setError(getErrorMessage(caught));
          isFailed = true;
        }
      });
      if (!isFailed) return null;
      // Send the user back to what they changed (the link, else the name)
      return isLinkChanged || isPatternChanged ? "link" : "name";
    },
    [kind, sourceId, onSaved, beforeLinkChange, runExclusive],
  );

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
            source_id: sourceId,
          });
          // Same preview id: SourcePreview keeps the user's drafts
          setPreview((prev) => (prev?.id === current.id ? { ...prev, result } : prev));
        } catch (caught: unknown) {
          setPreviewError(getErrorMessage(caught));
        }
      });
    },
    [preview, sourceId, runExclusive],
  );

  const savePreview = useCallback(
    async (options: WebSourceOptions): Promise<boolean> => {
      const current = preview;
      if (current === null) return false;
      let isSaved = false;
      await runExclusive("save", async () => {
        setPreviewError(null);
        try {
          const updated = await updateVacancySource(sourceId, {
            input: current.input,
            job_link_contains: options.jobLinkContains,
            name: options.name,
          });
          isSaved = true;
          onSaved(updated);
        } catch (caught: unknown) {
          setPreviewError(getErrorMessage(caught));
        }
      });
      return isSaved;
    },
    [preview, sourceId, onSaved, runExclusive],
  );

  const closePreview = useCallback((): void => {
    if (busyRef.current) return;
    setPreview(null);
    setPreviewError(null);
  }, []);

  return {
    busyAction,
    isBusy: busyAction !== null,
    error,
    preview,
    previewError,
    submit,
    recheck,
    savePreview,
    closePreview,
  };
}
