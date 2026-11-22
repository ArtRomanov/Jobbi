import type { components } from "@/shared/api";

/** One watched source (Telegram channel or company job board). */
export type VacancySource = components["schemas"]["VacancySourceRead"];

/** Where a source comes from: "telegram" | "greenhouse" | "lever" | "lever_eu". */
export type VacancySourceKind = VacancySource["kind"];

/** Search description and exclude words. */
export type VacancySearchSettings = components["schemas"]["VacancySearchSettingsRead"];

/** Body of PATCH /api/v1/vacancy-search-settings: a field left out stays unchanged. */
export type VacancySearchSettingsUpdate = components["schemas"]["VacancySearchSettingsUpdate"];

/** AI availability and daily-limit state of vacancy discovery. */
export type DiscoveryStatus = components["schemas"]["DiscoveryStatus"];

/** Response of GET /api/v1/vacancy-sources. */
export type VacancySourcesResponse = components["schemas"]["VacancySourcesResponse"];
