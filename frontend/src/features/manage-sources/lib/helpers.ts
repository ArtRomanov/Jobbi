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
