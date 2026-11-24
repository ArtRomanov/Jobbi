# Vacancy Source Entity

Sources the user watches for vacancies (Telegram channels; Greenhouse, Lever, Teamtailor and Ashby boards; web pages), plus the search settings and discovery status returned with them. Types are aliases of the generated OpenAPI schemas; API calls: `getVacancySources`, `previewVacancySource`, `addVacancySource`, `deleteVacancySource`, `updateVacancySource`, `updateSearchSettings`.

- `pending_count`: the source's posts waiting for the AI (web rows whose job page is not read yet don't count, same rule as the Inbox banner); the panel shows it when > 0.
- Each source has a stable `key` ("<kind>:<handle>", same across remove/re-add); the Inbox filters by it. `removed_sources` (`{key, label}[]`) lists card sources with no live source.
- `previewVacancySource({input, job_link_contains?, source_id?})` never saves: non-web kinds answer `{kind}` only; a web page answers `default_name`, `found_count` (first page) and ≤ 5 `titles`.
- `addVacancySource({input, job_link_contains?, name?})` sends raw user input; the backend parses and checks it live (up to ~10 s). Its 400/409 `detail` strings are user-facing — show them via `getErrorMessage` from `@/shared/api`.
- `DELETE` returns 204 with no body; the client turns that into `null`.
- Settings: `{description, keywords, keyword_filter}` (pre-AI keyword filter: a new post reaches the AI only if it contains a keyword, when the switch is on and the list is not empty). `status.filtered_last_24h` counts posts the filter skipped. The generated types keep `description` / `keywords` optional (Python defaults) — read them with `??`.
- `updateSearchSettings` is a partial PATCH (`VacancySearchSettingsUpdate` is `Partial<>` of the generated type, which wrongly requires `keyword_filter`) and returns the server-normalized settings (trimmed, empty description → `null`; keywords lowercased, inner whitespace collapsed, de-duped); show those, not what was sent. 400 `detail`: "You can add up to 50 keywords", "Keywords must be 1–64 characters".
- `updateVacancySource(id, patch)` is a partial PATCH (`name` now; `input` / `job_link_contains` in Slice 6) returning the updated source; `name: null` or "" → default name. `name_is_custom` tells whether `display_name` is the user's name.
