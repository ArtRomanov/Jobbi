/**
 * Client-side paging math for the Sources list (0-based page indexes).
 * Works over whatever list it is given, so a future in-panel search or
 * filter only has to pass the filtered list.
 */

/** Number of pages for `total` items; at least 1 (an empty list is one empty page). */
export function getPageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize));
}

/** Page that holds the item at `index`. */
export function getPageOfIndex(index: number, pageSize: number): number {
  return Math.floor(index / pageSize);
}

/** `page` kept inside 0 … pageCount - 1 (e.g. after the list shrank). */
export function clampPage(page: number, pageCount: number): number {
  return Math.min(Math.max(0, page), Math.max(0, pageCount - 1));
}

/** The items shown on `page`; the last page may be short. */
export function getPageItems<T>(items: readonly T[], page: number, pageSize: number): T[] {
  const start = page * pageSize;
  return items.slice(start, start + pageSize);
}
