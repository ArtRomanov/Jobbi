type Listener = () => void;

// Module-level so any slice can signal without a shared provider
const listeners = new Set<Listener>();

/**
 * Tell every `useNewVacancyCount` (and other subscribers) that Inbox cards
 * changed — a scan finished or the user acted on a card — so they refetch.
 */
export function notifyVacanciesChanged(): void {
  for (const listener of [...listeners]) listener();
}

/** Subscribe to `notifyVacanciesChanged`; returns the unsubscribe function. */
export function subscribeVacanciesChanged(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
