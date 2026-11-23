import type { components } from "@/shared/api";

/**
 * One watched source (Telegram channel, company job board or web page).
 * `name_is_custom`: the user renamed it (false → `display_name` is the default name).
 * `editable`: false while a first-scan attempt runs (Edit is disabled then).
 */
export type VacancySource = components["schemas"]["VacancySourceRead"];

/** Where a source comes from: "telegram" | "greenhouse" | "lever" | "lever_eu" | "teamtailor" | "ashby" | "web". */
export type VacancySourceKind = VacancySource["kind"];

/** A source of existing cards that matches no live source: `{key, label}` (shown "(removed)"). */
export type RemovedVacancySource = VacancySourcesResponse["removed_sources"][number];

/** Search description and exclude words. */
export type VacancySearchSettings = components["schemas"]["VacancySearchSettingsRead"];

/** Body of PATCH /api/v1/vacancy-search-settings: a field left out stays unchanged. */
export type VacancySearchSettingsUpdate = components["schemas"]["VacancySearchSettingsUpdate"];

/** AI availability and daily-limit state of vacancy discovery. */
export type DiscoveryStatus = components["schemas"]["DiscoveryStatus"];

/** Response of GET /api/v1/vacancy-sources. */
export type VacancySourcesResponse = components["schemas"]["VacancySourcesResponse"];

/** Body of POST /api/v1/vacancy-sources (`job_link_contains` and `name`: web pages only). */
export type VacancySourceCreate = components["schemas"]["VacancySourceCreate"];

/** Body of POST /api/v1/vacancy-sources/preview (`source_id`: the source being edited). */
export type VacancySourcePreviewRequest = components["schemas"]["VacancySourcePreviewRequest"];

/** A job board the previewed page links to (Slice 4). */
export type AtsHint = components["schemas"]["AtsHint"];

/**
 * Response of POST /api/v1/vacancy-sources/preview. Non-web kinds return only
 * `kind`; web adds the default name, the first-page count and up to 5 titles.
 */
export type VacancySourcePreview = components["schemas"]["VacancySourcePreview"];

/**
 * Body of PATCH /api/v1/vacancy-sources/{id}: a field left out stays unchanged.
 * `name`: null or "" → back to the default name. `input`: a new link — a web
 * source keeps its id; any other kind (or a kind change) is replaced by a NEW
 * source with a different id. `job_link_contains`: web pages only.
 */
export type VacancySourceUpdate = components["schemas"]["VacancySourceUpdate"];
