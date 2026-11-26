import { useCallback, useMemo, useRef, useState } from "react";
import { getErrorMessage } from "@/shared/api";
import { useToast } from "@/shared/ui";
import { updateSearchSettings } from "@/entities/vacancy-source";
import type { VacancySearchSettings } from "@/entities/vacancy-source";
import { DESCRIPTION_MAX_LENGTH, SAVED_MESSAGE } from "../lib/constants";
import { hasSearchSettingsChanges, normalizeDescription } from "../lib/search-settings-changes";
import type { UseSearchSettingsFormResult } from "./types";

/**
 * Drafts (description, keywords, keyword-filter switch) for the "What are you
 * looking for?" form. `initial` seeds them once (the form is re-mounted when
 * settings load) and stays the last saved value (the parent passes each save
 * back), so `isDirty` compares the drafts with it. Save PATCHes all three in
 * one request, then resets the drafts to the server-normalized values,
 * reports it via `onSaved` and toasts "Saved"; a failure becomes an inline error.
 */
export function useSearchSettingsForm(
  initial: VacancySearchSettings | null,
  onSaved: (settings: VacancySearchSettings) => void,
): UseSearchSettingsFormResult {
  const { showToast } = useToast();
  const [description, setDescriptionValue] = useState(initial?.description ?? "");
  const [keywords, setKeywordsValue] = useState<readonly string[]>(initial?.keywords ?? []);
  const [keywordFilter, setKeywordFilterValue] = useState(initial?.keyword_filter ?? true);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  // Guards against a second save before React re-renders with isSaving=true
  const isSavingRef = useRef(false);

  // maxLength stops typing; this also cuts text that bypasses it (e.g. paste)
  const setDescription = useCallback((value: string): void => {
    setDescriptionValue(value.slice(0, DESCRIPTION_MAX_LENGTH));
    setSaveError(null);
  }, []);

  const setKeywords = useCallback((value: readonly string[]): void => {
    setKeywordsValue(value);
    setSaveError(null);
  }, []);

  const setKeywordFilter = useCallback((value: boolean): void => {
    setKeywordFilterValue(value);
    setSaveError(null);
  }, []);

  const isDirty = useMemo(
    () =>
      initial !== null &&
      hasSearchSettingsChanges({ description, keywords, keywordFilter }, initial),
    [initial, description, keywords, keywordFilter],
  );

  const save = useCallback(async (): Promise<boolean> => {
    if (isSavingRef.current) return false;
    isSavingRef.current = true;
    setIsSaving(true);
    setSaveError(null);
    try {
      const saved = await updateSearchSettings({
        // Blank as the server sees it (Python strip, not JS trim); else the raw text
        description: normalizeDescription(description) === "" ? null : description,
        keywords: [...keywords],
        keyword_filter: keywordFilter,
      });
      setDescriptionValue(saved.description ?? "");
      setKeywordsValue(saved.keywords ?? []);
      setKeywordFilterValue(saved.keyword_filter);
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
  }, [description, keywords, keywordFilter, onSaved, showToast]);

  return {
    description,
    setDescription,
    keywords,
    setKeywords,
    keywordFilter,
    setKeywordFilter,
    isDirty,
    saveError,
    isSaving,
    save,
  };
}
