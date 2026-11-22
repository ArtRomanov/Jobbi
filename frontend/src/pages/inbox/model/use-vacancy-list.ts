import { useCallback, useEffect, useRef, useState } from "react";
import { getErrorMessage } from "@/shared/api";
import { listVacancies } from "@/entities/vacancy";
import type { Vacancy } from "@/entities/vacancy";
import { VACANCIES_PER_PAGE } from "../lib/constants";
import type { UseVacancyListResult, VacancyListLoadState } from "./types";

/**
 * Inbox list, newest first, loaded page by page ("Load more").
 * A change of `refreshKey` reloads the first page in the background: the
 * current cards stay visible until the new ones arrive.
 */
export function useVacancyList(refreshKey: number): UseVacancyListResult {
  const [items, setItems] = useState<Vacancy[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loadState, setLoadState] = useState<VacancyListLoadState>("loading");
  const [retryKey, setRetryKey] = useState(0);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  // Bumped by every first-page load, so a late "Load more" page is dropped
  const generationRef = useRef(0);
  const isLoadingMoreRef = useRef(false);

  useEffect(() => {
    generationRef.current += 1;
    const generation = generationRef.current;

    async function load(): Promise<void> {
      try {
        const data = await listVacancies({ sort: "date", page: 1, per_page: VACANCIES_PER_PAGE });
        if (generation !== generationRef.current) return;
        setItems(data.items);
        setTotal(data.total);
        setPage(1);
        setLoadMoreError(null);
        setLoadState("ready");
      } catch {
        if (generation !== generationRef.current) return;
        // A failed background refresh keeps the cards already shown
        setLoadState((state) => (state === "ready" ? state : "error"));
      }
    }

    void load();
    return () => {
      generationRef.current += 1;
    };
  }, [refreshKey, retryKey]);

  const loadMore = useCallback(async (): Promise<void> => {
    if (isLoadingMoreRef.current) return;
    isLoadingMoreRef.current = true;
    setIsLoadingMore(true);
    setLoadMoreError(null);
    const generation = generationRef.current;
    try {
      const nextPage = page + 1;
      const data = await listVacancies({
        sort: "date",
        page: nextPage,
        per_page: VACANCIES_PER_PAGE,
      });
      if (generation !== generationRef.current) return;
      setItems((current) => {
        const known = new Set(current.map((item) => item.id));
        return [...current, ...data.items.filter((item) => !known.has(item.id))];
      });
      setTotal(data.total);
      setPage(nextPage);
    } catch (error: unknown) {
      if (generation === generationRef.current) setLoadMoreError(getErrorMessage(error));
    } finally {
      isLoadingMoreRef.current = false;
      setIsLoadingMore(false);
    }
  }, [page]);

  const retry = useCallback((): void => {
    setLoadState("loading");
    setRetryKey((key) => key + 1);
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
  };
}
