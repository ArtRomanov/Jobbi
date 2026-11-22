# Inbox Page

Route `/inbox`. Composes the vacancy list (`VacancyCard` from `entities/vacancy`) and the Sources panel (`features/manage-sources`).

- The page owns `refreshKey`; `SourcesPanel`'s `onScanFinished` bumps it so first-scan results appear without a reload. A refresh reloads page 1 in the background (cards stay visible; a failed refresh keeps them).
- List: date sort (newest first), 20 per page, "Load more" appends and dedupes by id; a page that arrives after a refresh is dropped.
- Filters, sort control and card actions arrive in later slices of spec 009.
