# Vacancy Source Entity

Sources the user watches for vacancies (Telegram channels now; Greenhouse/Lever boards later), plus the search settings and discovery status returned with them. Types are aliases of the generated OpenAPI schemas; API calls: `getVacancySources`, `addVacancySource`, `deleteVacancySource`.

- `addVacancySource` sends raw user input; the backend parses and checks it live (up to ~10 s). Its 400/409 `detail` strings are user-facing — show them via `getErrorMessage` from `@/shared/api`.
- `DELETE` returns 204 with no body; the client turns that into `null`.
