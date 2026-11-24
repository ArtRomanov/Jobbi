# Vacancy Source Entity

Sources the user watches for vacancies (Telegram channels; Greenhouse, Lever, Teamtailor and Ashby boards; web pages), plus the search settings and discovery status returned with them. Types are aliases of the generated OpenAPI schemas; API calls: `getVacancySources`, `previewVacancySource`, `addVacancySource`, `deleteVacancySource`, `updateVacancySource`, `updateSearchSettings`.

- Each source has a stable `key` ("<kind>:<handle>", same across remove/re-add); the Inbox filters by it. `removed_sources` (`{key, label}[]`) lists card sources with no live source.
- `previewVacancySource({input, job_link_contains?, source_id?})` never saves: non-web kinds answer `{kind}` only; a web page answers `default_name`, `found_count` (first page) and ≤ 5 `titles`.
- `addVacancySource({input, job_link_contains?, name?})` sends raw user input; the backend parses and checks it live (up to ~10 s). Its 400/409 `detail` strings are user-facing — show them via `getErrorMessage` from `@/shared/api`.
- `DELETE` returns 204 with no body; the client turns that into `null`.
- `updateSearchSettings` is a partial PATCH and returns the server-normalized settings (trimmed, exclude terms lowercased + deduped, empty description → `null`); show those, not what was sent.
- `updateVacancySource(id, patch)` is a partial PATCH (`name` now; `input` / `job_link_contains` in Slice 6) returning the updated source; `name: null` or "" → default name. `name_is_custom` tells whether `display_name` is the user's name.
- Exclude words are hidden since spec 012: the UI neither shows nor sends `exclude`, but the field stays in the API types (and the stored words in the DB) until backlog #12 removes it.
