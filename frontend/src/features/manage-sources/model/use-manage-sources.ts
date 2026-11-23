import { useCallback, useEffect, useRef, useState } from "react";
import { handleApiError } from "@/shared/api";
import { useToast } from "@/shared/ui";
import { deleteVacancySource, getVacancySources } from "@/entities/vacancy-source";
import { notifyVacanciesChanged } from "@/entities/vacancy";
import type {
  DiscoveryStatus,
  RemovedVacancySource,
  VacancySearchSettings,
  VacancySource,
} from "@/entities/vacancy-source";
import { getPollInterval, hasScanFinished, mergePolledSources } from "../lib/helpers";
import type { SourcesChangeHandler, SourcesLoadState, UseManageSourcesResult } from "./types";

/**
 * Owns the Sources panel: initial load (with retry) of sources and the saved
 * search settings, appending a source created by the add flow
 * (`useAddSource`) and removing one (toast on failure).
 *
 * Adding is blocked until the initial load succeeds, so a late GET can never
 * overwrite a source the user just added.
 *
 * After the initial load one polling chain re-fetches the list (status fields
 * only) and the discovery `status`: every 5 s while any source is scanning,
 * else every 60 s while the page is visible (paused when hidden, resumed on
 * return). When a scan ends, `onScanFinished` runs and
 * `notifyVacanciesChanged()` fires so new cards and the badge appear.
 *
 * `onSourcesChange` receives the live sources and the removed sources that
 * cards still reference whenever either changes (the Inbox source filter).
 * After a removal, the removed list is re-fetched in the background.
 */
export function useManageSources(
  onScanFinished?: () => void,
  onSourcesChange?: SourcesChangeHandler,
): UseManageSourcesResult {
  const { showToast } = useToast();
  const [sources, setSources] = useState<VacancySource[]>([]);
  const [removedSources, setRemovedSources] = useState<readonly RemovedVacancySource[]>([]);
  const [settings, setSettings] = useState<VacancySearchSettings | null>(null);
  const [status, setStatus] = useState<DiscoveryStatus | null>(null);
  const [loadState, setLoadState] = useState<SourcesLoadState>("loading");
  const [reloadKey, setReloadKey] = useState(0);
  const [removingIds, setRemovingIds] = useState<ReadonlySet<string>>(() => new Set());
  const isReady = loadState === "ready";
  const isAddDisabled = !isReady;
  const isAnyScanning = sources.some((source) => source.scanning);
  // Latest values for the polling loop, so it does not restart on every render
  const sourcesRef = useRef(sources);
  const onScanFinishedRef = useRef(onScanFinished);
  const onSourcesChangeRef = useRef(onSourcesChange);
  useEffect(() => {
    sourcesRef.current = sources;
    onScanFinishedRef.current = onScanFinished;
    onSourcesChangeRef.current = onSourcesChange;
  });
  // Latest removed-list refetch wins; bumped on unmount to drop late responses
  const removedRequestRef = useRef(0);
  useEffect(
    () => () => {
      removedRequestRef.current += 1;
    },
    [],
  );

  useEffect(() => {
    onSourcesChangeRef.current?.(sources, removedSources);
  }, [sources, removedSources]);

  useEffect(() => {
    let cancelled = false;

    async function load(): Promise<void> {
      try {
        const data = await getVacancySources();
        if (cancelled) return;
        setSources(data.sources);
        setRemovedSources(data.removed_sources);
        setSettings(data.settings);
        setStatus(data.status);
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
    if (!isReady) return;
    let cancelled = false;
    let isPolling = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let lastPollAt = Date.now();
    const interval = getPollInterval(isAnyScanning);
    // Scan polls always run (scan end refreshes cards + badge); the slow status
    // refresh only runs while the page is visible
    const shouldRun = (): boolean => isAnyScanning || document.visibilityState === "visible";

    function schedule(delay: number): void {
      clearTimeout(timer);
      timer = setTimeout(() => void tick(), delay);
    }

    async function tick(): Promise<void> {
      // Hidden page: stop here; `handleVisibilityChange` resumes the chain
      if (cancelled || !shouldRun()) return;
      isPolling = true;
      lastPollAt = Date.now();
      // A poll is a removed-list read too: newest request wins over an older refresh
      removedRequestRef.current += 1;
      const removedRequestId = removedRequestRef.current;
      try {
        const data = await getVacancySources();
        if (cancelled) return;
        const isFinished = hasScanFinished(sourcesRef.current, data.sources);
        setSources((current) => mergePolledSources(current, data.sources));
        if (removedRequestId === removedRequestRef.current) {
          setRemovedSources(data.removed_sources);
          setStatus(data.status);
        }
        if (isFinished) {
          onScanFinishedRef.current?.();
          notifyVacanciesChanged();
        }
      } catch {
        // A failed poll is retried on the next tick
      } finally {
        isPolling = false;
        // Cleanup clears this timer when the cadence changes or the panel unmounts
        if (!cancelled) schedule(interval);
      }
    }

    // Back on the page: poll as soon as a full interval has passed since the last one
    function handleVisibilityChange(): void {
      if (document.visibilityState !== "visible" || isPolling) return;
      schedule(Math.max(0, interval - (Date.now() - lastPollAt)));
    }

    schedule(interval);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [isAnyScanning, isReady]);

  const appendSource = useCallback((source: VacancySource): void => {
    setSources((prev) => [...prev, source]);
  }, []);

  // Edit: the server's copy replaces the row in place (order kept)
  const replaceSource = useCallback((source: VacancySource): void => {
    setSources((prev) => prev.map((item) => (item.id === source.id ? source : item)));
  }, []);

  const refreshRemovedSources = useCallback(async (): Promise<void> => {
    removedRequestRef.current += 1;
    const requestId = removedRequestRef.current;
    try {
      const data = await getVacancySources();
      if (requestId === removedRequestRef.current) {
        setRemovedSources(data.removed_sources);
        setStatus(data.status);
      }
    } catch {
      // The removed list only feeds the Inbox filter; the next load fixes it
    }
  }, []);

  const removeSource = useCallback(
    async (id: string): Promise<boolean> => {
      setRemovingIds((prev) => new Set(prev).add(id));
      try {
        await deleteVacancySource(id);
        setSources((prev) => prev.filter((source) => source.id !== id));
        // Its cards now belong to a removed source; the server knows which remain
        void refreshRemovedSources();
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
    [showToast, refreshRemovedSources],
  );

  const retryLoad = useCallback((): void => {
    setLoadState("loading");
    setReloadKey((key) => key + 1);
  }, []);

  return {
    sources,
    settings,
    setSettings,
    status,
    loadState,
    removingIds,
    isAddDisabled,
    appendSource,
    replaceSource,
    removeSource,
    retryLoad,
  };
}
