import type { VacancySource } from "@/entities/vacancy-source";

/**
 * Which source should receive focus after `removedId` is removed: the next one
 * in display order, else the previous one, else null (list is now empty).
 * `isPresent` filters out ids that are gone already (e.g. concurrent removes).
 */
export function pickFocusAfterRemove(
  orderedIds: readonly string[],
  removedId: string,
  isPresent: (id: string) => boolean,
): string | null {
  const index = orderedIds.indexOf(removedId);
  const isCandidate = (id: string): boolean => id !== removedId && isPresent(id);

  for (let i = index + 1; i < orderedIds.length; i += 1) {
    const id = orderedIds[i];
    if (id !== undefined && isCandidate(id)) return id;
  }
  for (let i = index - 1; i >= 0; i -= 1) {
    const id = orderedIds[i];
    if (id !== undefined && isCandidate(id)) return id;
  }
  return null;
}

/**
 * Apply polled status fields to the local list. Membership stays local, so a
 * poll that started before an add/remove can never undo it.
 */
export function mergePolledSources(
  current: readonly VacancySource[],
  polled: readonly VacancySource[],
): VacancySource[] {
  const byId = new Map(polled.map((source) => [source.id, source]));
  return current.map((source) => {
    const fresh = byId.get(source.id);
    return fresh
      ? {
          ...source,
          scanning: fresh.scanning,
          last_checked_at: fresh.last_checked_at,
          unavailable: fresh.unavailable,
          last_error: fresh.last_error,
        }
      : source;
  });
}

/** True when a source that was scanning in `before` is present and not scanning in `after`. */
export function hasScanFinished(
  before: readonly VacancySource[],
  after: readonly VacancySource[],
): boolean {
  const scanningAfter = new Map(after.map((source) => [source.id, source.scanning]));
  return before.some((source) => source.scanning && scanningAfter.get(source.id) === false);
}
