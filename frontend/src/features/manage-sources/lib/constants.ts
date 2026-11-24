import type { VacancySourceKind } from "@/entities/vacancy-source";

/** Human label for each source kind, shown next to the source name. */
export const SOURCE_KIND_LABELS: Record<VacancySourceKind, string> = {
  telegram: "Telegram",
  greenhouse: "Greenhouse",
  lever: "Lever",
  lever_eu: "Lever",
};

export const SCANNING_LABEL = "Scanning…";
export const UNAVAILABLE_LABEL = "Unavailable";
/** Shown after "Unavailable —" if the server sent no reason. */
export const UNAVAILABLE_FALLBACK_REASON = "Could not reach the source";
export const LAST_CHECKED_PREFIX = "Last checked";
/** How often the source list is re-fetched while any source is scanning. */
export const SCAN_POLL_INTERVAL_MS = 5000;
/** How often sources + status are re-fetched otherwise (only while the page is visible). */
export const STATUS_POLL_INTERVAL_MS = 60_000;
export const AI_UNAVAILABLE_NOTICE =
  "Vacancy search is temporarily unavailable — new posts will be checked when it's back";
export const LOAD_ERROR_MESSAGE = "Could not load your sources.";
export const NO_SOURCES_MESSAGE = "You are not watching any sources yet.";
export const SOURCE_INPUT_PLACEHOLDER = "@channel or t.me/channel";

export const DESCRIPTION_MAX_LENGTH = 500;
export const NO_DESCRIPTION_HINT = "Describe what you're looking for to start finding vacancies.";
export const SAVED_MESSAGE = "Saved";
export const DESCRIPTION_PLACEHOLDER =
  "Senior frontend, React or Vue, remote or EU, from 4000 €, no outsourcing";
