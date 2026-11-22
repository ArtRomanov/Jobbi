# Vacancy Entity

Inbox cards found by the discovery worker. Types are aliases of the generated OpenAPI schemas; API: `listVacancies(params)`, `getNewVacancyCount()`, `markVacancySeen` / `dismissVacancy` / `restoreVacancy` (POST, 204). UI: `VacancyCard` (display only, `actions` slot for feature buttons).

- `VacancyCard` text is plain text (React escaping), never HTML. "Show more" only expands the text — it must never mark the card seen (functional spec 2.3).
- `notifyVacanciesChanged()` is a module-level signal (`model/vacancies-changed.ts`), not React state: call it after anything that changes cards (scan finished, card action). `useNewVacancyCount` refetches on it and on every route change; the latest response wins and errors keep the last count.
- `sources` on a card are `{key, label}`: show `label`, filter by `key` (`listVacancies({ source: key })`). Keys are stable across remove/re-add. Merged reposts have several sources: the card shows "Posted in: A, B" (`formatCardSources`); one source shows just its label.
- `addVacancyToTracker(id, body)` (POST, 201). Its "already tracked" 409 has an OBJECT `detail` (`{message, application}`), unlike every other error's string `detail`: read it with `getDuplicateApplication(error)` (null for anything else). Cards carry the same ref as `existing_application`.
- Fit labels/tones live in `lib/constants.ts`; `Badge` tones come from `@/shared/ui`.
