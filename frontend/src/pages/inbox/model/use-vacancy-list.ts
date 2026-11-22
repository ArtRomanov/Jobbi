import { useCallback, useEffect, useRef, useState } from "react";
import { getErrorMessage } from "@/shared/api";
import { listVacancies } from "@/entities/vacancy";
import type { Vacancy } from "@/entities/vacancy";
import type { InboxFilterValues } from "@/features/inbox-filters";
import { buildListParams, insertAt } from "../lib/helpers";
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
  // Cards removed since the last page-1 load, with where they stood: Undo puts
  // them back in place, and its size is how far server pages have shifted
  const removedIndexesRef = useRef(new Map<string, number>());

  useEffect(() => {
    generationRef.current += 1;
    const generation = generationRef.current;
    const filtersKey = JSON.stringify([source, state, sort]);
    if (lastFiltersKeyRef.current !== null && lastFiltersKeyRef.current !== filtersKey) {
      setLoadState("loading");
    }
    lastFiltersKeyRef.current = filtersKey;
    // The new page 1 decides what is listed; a later Undo must not insert into it
    removedIndexesRef.current.clear();

    async function load(): Promise<void> {
      try {
        const data = await listVacancies(buildListParams({ source, state, sort }, 1));
        if (generation !== generationRef.current) return;
        setList({ items: data.items, total: data.total });
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
        removedIndexesRef.current.size > 0
          ? [nextPage - 1, nextPage].map((p) => listVacancies(buildListParams(params, p)))
          : [listVacancies(buildListParams(params, nextPage))],
      );
      if (generation !== generationRef.current) return;
      const fetched = pages.flatMap((data) => data.items);
      const fetchedTotal = pages[pages.length - 1]?.total ?? 0;
      setList((current) => {
        const known = new Set(current.items.map((item) => item.id));
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
      // Idempotent write, safe if React runs the updater twice
      removedIndexesRef.current.set(id, index);
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
    setList((current) => {
      if (current.items.some((item) => item.id === vacancy.id)) return current;
      return { items: insertAt(current.items, index, vacancy), total: current.total + 1 };
    });
  }, []);

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
