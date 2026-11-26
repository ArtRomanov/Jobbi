import { useCallback, useMemo, useState } from "react";
import type { VacancySource } from "@/entities/vacancy-source";
import { SOURCES_PAGE_SIZE } from "../lib/constants";
import { clampPage, getPageCount, getPageItems, getPageOfIndex } from "../lib/paging";
import type { UseSourcePagesResult } from "./types";

/**
 * Client-side paging of the Sources list (`SOURCES_PAGE_SIZE` per page) over
 * the full list from `useManageSources`. Pass the list to page over: a future
 * in-panel search / filter passes its filtered list and calls `setPage(0)`
 * when the query changes.
 *
 * The page is adjusted during render (no effect, no flash of a wrong page):
 * a pending `revealSource` id jumps to the page that holds it, and the page is
 * clamped when the list shrinks (removing the last row of the last page shows
 * the previous page).
 */
export function useSourcePages(sources: readonly VacancySource[]): UseSourcePagesResult {
  const [page, setPageState] = useState(0);
  const [revealId, setRevealId] = useState<string | null>(null);
  const pageCount = getPageCount(sources.length, SOURCES_PAGE_SIZE);

  let nextPage = page;
  if (revealId !== null) {
    const index = sources.findIndex((source) => source.id === revealId);
    if (index !== -1) {
      nextPage = getPageOfIndex(index, SOURCES_PAGE_SIZE);
      setRevealId(null);
    }
  }
  nextPage = clampPage(nextPage, pageCount);
  if (nextPage !== page) setPageState(nextPage);

  const pageSources = useMemo(
    () => getPageItems(sources, nextPage, SOURCES_PAGE_SIZE),
    [sources, nextPage],
  );

  const setPage = useCallback(
    (target: number): void => setPageState(clampPage(target, pageCount)),
    [pageCount],
  );

  const revealSource = useCallback((id: string): void => setRevealId(id), []);

  return { page: nextPage, pageCount, pageSources, setPage, revealSource };
}
