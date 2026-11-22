# Vacancy Source Entity

Sources the user watches for vacancies (Telegram channels now; Greenhouse/Lever boards later), plus the search settings and discovery status returned with them. Types are aliases of the generated OpenAPI schemas; API calls: `getVacancySources`, `addVacancySource`, `deleteVacancySource`, `updateSearchSettings`.

- Each source has a stable `key` ("<kind>:<handle>", same across remove/re-add); the Inbox filters by it. `removed_sources` (`{key, label}[]`) lists card sources with no live source.
- `addVacancySource` sends raw user input; the backend parses and checks it live (up to ~10 s). Its 400/409 `detail` strings are user-facing — show them via `getErrorMessage` from `@/shared/api`.
- `DELETE` returns 204 with no body; the client turns that into `null`.
- `updateSearchSettings` is a partial PATCH and returns the server-normalized settings (trimmed, exclude terms lowercased + deduped, empty description → `null`); show those, not what was sent.
