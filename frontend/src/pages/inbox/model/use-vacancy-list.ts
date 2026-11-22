import { useCallback, useEffect, useRef, useState } from "react";
import { getErrorMessage } from "@/shared/api";
import { listVacancies } from "@/entities/vacancy";
import type { Vacancy } from "@/entities/vacancy";
import type { InboxFilterValues } from "@/features/inbox-filters";
import { buildListParams, insertAt, matchesStateFilter } from "../lib/helpers";
import type { UseVacancyListResult, VacancyListLoadState, VacancyListState } from "./types";

const EMPTY_LIST: VacancyListState = { items: [], total: 0 };

/**
 * Inbox list for the given filters, loaded page by page ("Load more").
 * A change of `refreshKey` reloads the first page in the background: the
 * current cards stay visible until the new ones arrive. A change of filters
 * shows the loading state, since the current cards no longer match.
 */
export function useVacancyList(
  refreshKey: number,
  filters: InboxFilterValues,
): UseVacancyListResult {
  const { source, state, sort } = filters;
  // One state, so remove/restore update cards and total in one pure updater
  const [list, setList] = useState<VacancyListState>(EMPTY_LIST);
  const { items, total } = list;
  const [page, setPage] = useState(1);
  const [loadState, setLoadState] = useState<VacancyListLoadState>("loading");
  const [retryKey, setRetryKey] = useState(0);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  // Bumped by every first-page load, so a late "Load more" page is dropped
  const generationRef = useRef(0);
  const isLoadingMoreRef = useRef(false);
  const lastFiltersKeyRef = useRef<string | null>(null);
  // Cards removed locally and not restored, with where they stand in the
  // current list: Undo puts them back in place, and a page-1 load that still
  // lists them (its request raced the dismiss) hides them
  const removedIndexesRef = useRef(new Map<string, number>());
  // Set by a local remove since the last page-1 load: server pages may have
  // shifted, so "Load more" re-reads the previous page too
  const hasShiftedRef = useRef(false);

  useEffect(() => {
    generationRef.current += 1;
    const generation = generationRef.current;
    const filtersKey = JSON.stringify([source, state, sort]);
    if (lastFiltersKeyRef.current !== null && lastFiltersKeyRef.current !== filtersKey) {
      setLoadState("loading");
    }
    lastFiltersKeyRef.current = filtersKey;

    async function load(): Promise<void> {
      try {
        const data = await listVacancies(buildListParams({ source, state, sort }, 1));
        if (generation !== generationRef.current) return;
        // Read on arrival, not when the request was sent: a dismiss that lands
        // while the request is in flight must not bring its card back
        const removed = removedIndexesRef.current;
        const stillRemoved = new Map<string, number>();
        data.items.forEach((item, index) => {
          if (removed.has(item.id)) stillRemoved.set(item.id, index);
        });
        // Cards the server no longer lists are out of this list for good, so a
        // later Undo does not insert them; the next load shows them if restored
        removedIndexesRef.current = stillRemoved;
        hasShiftedRef.current = stillRemoved.size > 0;
        setList({
          items: data.items.filter((item) => !stillRemoved.has(item.id)),
          total: Math.max(0, data.total - stillRemoved.size),
        });
        setPage(1);
        setLoadMoreError(null);
        setLoadState("ready");
      } catch {
        if (generation !== generationRef.current) return;
        // A failed background refresh keeps the cards already shown
        setLoadState((current) => (current === "ready" ? current : "error"));
      }
    }

    void load();
    return () => {
      generationRef.current += 1;
    };
  }, [refreshKey, retryKey, source, state, sort]);

  const loadMore = useCallback(async (): Promise<void> => {
    if (isLoadingMoreRef.current) return;
    isLoadingMoreRef.current = true;
    setIsLoadingMore(true);
    setLoadMoreError(null);
    const generation = generationRef.current;
    try {
      const nextPage = page + 1;
      const params = { source, state, sort };
      // Removed cards shift later cards onto earlier server pages; re-reading
      // the previous page too (deduped by id) keeps them from being skipped
      const pages = await Promise.all(
        hasShiftedRef.current
          ? [nextPage - 1, nextPage].map((p) => listVacancies(buildListParams(params, p)))
          : [listVacancies(buildListParams(params, nextPage))],
      );
      if (generation !== generationRef.current) return;
      const fetched = pages.flatMap((data) => data.items);
      // The server still counts listed cards whose dismiss has not landed
      const removed = removedIndexesRef.current;
      const hiddenCount = new Set(fetched.filter((item) => removed.has(item.id)).map((item) => item.id)).size;
      const fetchedTotal = Math.max(0, (pages[pages.length - 1]?.total ?? 0) - hiddenCount);
      setList((current) => {
        // Locally removed cards count as known: a re-read page may still list
        // one whose dismiss has not landed yet
        const known = new Set([
          ...current.items.map((item) => item.id),
          ...removedIndexesRef.current.keys(),
        ]);
        const added = fetched.filter((item) => {
          if (known.has(item.id)) return false;
          known.add(item.id);
          return true;
        });
        return { items: [...current.items, ...added], total: fetchedTotal };
      });
      setPage(nextPage);
    } catch (error: unknown) {
      if (generation === generationRef.current) setLoadMoreError(getErrorMessage(error));
    } finally {
      isLoadingMoreRef.current = false;
      setIsLoadingMore(false);
    }
  }, [page, source, state, sort]);

  const retry = useCallback((): void => {
    setLoadState("loading");
    setRetryKey((key) => key + 1);
  }, []);

  const updateItem = useCallback((vacancy: Vacancy): void => {
    setList((current) => ({
      ...current,
      items: current.items.map((item) => (item.id === vacancy.id ? vacancy : item)),
    }));
  }, []);

  const removeItem = useCallback((id: string): void => {
    setList((current) => {
      const index = current.items.findIndex((item) => item.id === id);
      if (index === -1) return current;
      // Idempotent writes, safe if React runs the updater twice
      removedIndexesRef.current.set(id, index);
      hasShiftedRef.current = true;
      return {
        items: current.items.filter((item) => item.id !== id),
        total: Math.max(0, current.total - 1),
      };
    });
  }, []);

  const restoreItem = useCallback((vacancy: Vacancy): void => {
    const index = removedIndexesRef.current.get(vacancy.id);
    // Not removed from the current list (a reload or filter change came between):
    // the next load shows the card where the server puts it
    if (index === undefined) return;
    removedIndexesRef.current.delete(vacancy.id);
    // Undo brings it back as seen; a New-only list must not show it (the server
    // has it out of this filter, so the total stays as is too)
    if (!matchesStateFilter(vacancy.state, state)) return;
    setList((current) => {
      if (current.items.some((item) => item.id === vacancy.id)) return current;
      return { items: insertAt(current.items, index, vacancy), total: current.total + 1 };
    });
  }, [state]);

  return {
    items,
    total,
    loadState,
    hasMore: items.length < total,
    isLoadingMore,
    loadMoreError,
    loadMore,
    retry,
    updateItem,
    removeItem,
    restoreItem,
  };
}
