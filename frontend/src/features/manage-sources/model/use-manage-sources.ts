import { useCallback, useEffect, useRef, useState } from "react";
import { getErrorMessage, handleApiError } from "@/shared/api";
import { useToast } from "@/shared/ui";
import {
  addVacancySource,
  deleteVacancySource,
  getVacancySources,
} from "@/entities/vacancy-source";
import { notifyVacanciesChanged } from "@/entities/vacancy";
import type { VacancySearchSettings, VacancySource } from "@/entities/vacancy-source";
import { SCAN_POLL_INTERVAL_MS } from "../lib/constants";
import { hasScanFinished, mergePolledSources } from "../lib/helpers";
import type { SourcesLoadState, UseManageSourcesResult } from "./types";

/**
 * Owns the Sources panel: initial load (with retry) of sources and the saved
 * search settings, adding a source from the
 * input (inline error on failure, input cleared on success) and removing one
 * (toast on failure).
 *
 * Adding is blocked until the initial load succeeds, so a late GET can never
 * overwrite a source the user just added.
 *
 * While any source is scanning, the list is re-fetched every 5 s (status
 * fields only). When a scan ends, `onScanFinished` runs and
 * `notifyVacanciesChanged()` fires so new cards and the badge appear.
 */
export function useManageSources(onScanFinished?: () => void): UseManageSourcesResult {
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
  const isAnyScanning = sources.some((source) => source.scanning);
  // Latest values for the polling loop, so it does not restart on every render
  const sourcesRef = useRef(sources);
  const onScanFinishedRef = useRef(onScanFinished);
  useEffect(() => {
    sourcesRef.current = sources;
    onScanFinishedRef.current = onScanFinished;
  });

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

  useEffect(() => {
    if (!isAnyScanning) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll(): Promise<void> {
      try {
        const data = await getVacancySources();
        if (cancelled) return;
        const isFinished = hasScanFinished(sourcesRef.current, data.sources);
        setSources((current) => mergePolledSources(current, data.sources));
        if (isFinished) {
          onScanFinishedRef.current?.();
          notifyVacanciesChanged();
        }
      } catch {
        // A failed poll is retried on the next tick
      } finally {
        // Cleanup clears this timer when scanning stops or the panel unmounts
        if (!cancelled) timer = setTimeout(() => void poll(), SCAN_POLL_INTERVAL_MS);
      }
    }

    timer = setTimeout(() => void poll(), SCAN_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [isAnyScanning]);

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
