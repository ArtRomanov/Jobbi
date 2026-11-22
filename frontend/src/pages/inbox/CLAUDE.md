# Inbox Page

Route `/inbox`. Composes the filter bar (`features/inbox-filters`), the vacancy list (`VacancyCard` from `entities/vacancy` + `VacancyActions` from `features/vacancy-actions` in its `actions` slot) and the Sources panel (`features/manage-sources`).

- The page owns `refreshKey`, the filter values and the source lists. `SourcesPanel`'s `onScanFinished` bumps `refreshKey`; its `onSourcesChange` mirrors live + removed sources into the filter (no extra GET).
- A refresh reloads page 1 in the background (cards stay visible; a failed refresh keeps them). A filter change shows the loading state and reloads page 1 with the combined params.
- List: 20 per page, "Load more" appends and dedupes by id; a page that arrives after a refresh is dropped.
- `VacancyList` mounts `useVacancyActions` once, so unmounting the list (leaving the page) ends the Undo window. `removeItem` remembers the card's index and `restoreItem` puts it back there; every page-1 load clears those indexes, so an Undo after a reload/filter change does not insert (the next load shows the card).
- After a dismiss or a successful "Add to tracker" (`completeAdd`), focus goes to the Dismiss button of the card that takes its place, else the one before, else the page `h1` (`PageHeader titleRef`).
- While cards are removed locally (remembered indexes > 0), "Load more" fetches the previous and the next server page in parallel and dedupes by id, because removals shift cards onto earlier pages.
- Empty state: "No vacancies yet…" with default filters, "No vacancies match these filters." otherwise.
