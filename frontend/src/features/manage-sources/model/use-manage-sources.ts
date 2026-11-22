import { useCallback, useEffect, useRef, useState } from "react";
import { getErrorMessage, handleApiError } from "@/shared/api";
import { useToast } from "@/shared/ui";
import {
  addVacancySource,
  deleteVacancySource,
  getVacancySources,
} from "@/entities/vacancy-source";
import type { VacancySearchSettings, VacancySource } from "@/entities/vacancy-source";
import type { SourcesLoadState, UseManageSourcesResult } from "./types";

/**
 * Owns the Sources panel: initial load (with retry) of sources and the saved
 * search settings, adding a source from the
 * input (inline error on failure, input cleared on success) and removing one
 * (toast on failure).
 *
 * Adding is blocked until the initial load succeeds, so a late GET can never
 * overwrite a source the user just added.
 */
export function useManageSources(): UseManageSourcesResult {
  const { showToast } = useToast();
  const [sources, setSources] = useState<VacancySource[]>([]);
  const [settings, setSettings] = useState<VacancySearchSettings | null>(null);
  const [loadState, setLoadState] = useState<SourcesLoadState>("loading");
  const [reloadKey, setReloadKey] = useState(0);
  const [input, setInputValue] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [isAdding, setIsAdding] = useState(false);
  const [removingIds, setRemovingIds] = useState<ReadonlySet<string>>(() => new Set());
  // Guards against a second submit before React re-renders with isAdding=true
  const isAddingRef = useRef(false);
  const isAddDisabled = loadState !== "ready";

  useEffect(() => {
    let cancelled = false;

    async function load(): Promise<void> {
      try {
        const data = await getVacancySources();
        if (cancelled) return;
        setSources(data.sources);
        setSettings(data.settings);
        setLoadState("ready");
      } catch {
        if (!cancelled) setLoadState("error");
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const setInput = useCallback((value: string): void => {
    setInputValue(value);
    setAddError(null);
  }, []);

  const addSource = useCallback(async (): Promise<void> => {
    const value = input.trim();
    if (value === "" || isAddDisabled || isAddingRef.current) return;
    isAddingRef.current = true;
    setIsAdding(true);
    setAddError(null);
    try {
      const created = await addVacancySource(value);
      setSources((prev) => [...prev, created]);
      setInputValue("");
    } catch (error: unknown) {
      setAddError(getErrorMessage(error));
    } finally {
      isAddingRef.current = false;
      setIsAdding(false);
    }
  }, [input, isAddDisabled]);

  const removeSource = useCallback(
    async (id: string): Promise<boolean> => {
      setRemovingIds((prev) => new Set(prev).add(id));
      try {
        await deleteVacancySource(id);
        setSources((prev) => prev.filter((source) => source.id !== id));
        return true;
      } catch (error: unknown) {
        handleApiError(error, showToast);
        return false;
      } finally {
        setRemovingIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      }
    },
    [showToast],
  );

  const retryLoad = useCallback((): void => {
    setLoadState("loading");
    setReloadKey((key) => key + 1);
  }, []);

  return {
    sources,
    settings,
    setSettings,
    loadState,
    input,
    setInput,
    addError,
    isAdding,
    removingIds,
    isAddDisabled,
    addSource,
    removeSource,
    retryLoad,
  };
}
