import { useCallback, useRef, useState } from "react";
import { getErrorMessage } from "@/shared/api";
import { useToast } from "@/shared/ui";
import { updateSearchSettings } from "@/entities/vacancy-source";
import type { VacancySearchSettings } from "@/entities/vacancy-source";
import { DESCRIPTION_MAX_LENGTH, SAVED_MESSAGE } from "../lib/constants";
import type { UseSearchSettingsFormResult } from "./types";

/**
 * Draft description for the "What are you looking for?" form. `initial` seeds
 * the draft once (the form is re-mounted when settings load). Save PATCHes
 * the description, then shows the server-normalized value,
 * reports it via `onSaved` and toasts "Saved"; a failure becomes an inline error.
 */
export function useSearchSettingsForm(
  initial: VacancySearchSettings | null,
  onSaved: (settings: VacancySearchSettings) => void,
): UseSearchSettingsFormResult {
  const { showToast } = useToast();
  const [description, setDescriptionValue] = useState(initial?.description ?? "");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  // Guards against a second save before React re-renders with isSaving=true
  const isSavingRef = useRef(false);

  // maxLength stops typing; this also cuts text that bypasses it (e.g. paste)
  const setDescription = useCallback((value: string): void => {
    setDescriptionValue(value.slice(0, DESCRIPTION_MAX_LENGTH));
    setSaveError(null);
  }, []);

  const save = useCallback(async (): Promise<boolean> => {
    if (isSavingRef.current) return false;
    isSavingRef.current = true;
    setIsSaving(true);
    setSaveError(null);
    try {
      const saved = await updateSearchSettings({
        description: description.trim() === "" ? null : description,
      });
      setDescriptionValue(saved.description ?? "");
      onSaved(saved);
      showToast(SAVED_MESSAGE, "success");
      return true;
    } catch (error: unknown) {
      setSaveError(getErrorMessage(error));
      return false;
    } finally {
      isSavingRef.current = false;
      setIsSaving(false);
    }
  }, [description, onSaved, showToast]);

  return { description, setDescription, saveError, isSaving, save };
}
