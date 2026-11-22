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
export const LOAD_ERROR_MESSAGE = "Could not load your sources.";
export const NO_SOURCES_MESSAGE = "You are not watching any sources yet.";
export const SOURCE_INPUT_PLACEHOLDER = "@channel or t.me/channel";

export const DESCRIPTION_MAX_LENGTH = 500;
export const EXCLUDE_MAX_ITEMS = 50;
export const EXCLUDE_TERM_MAX_LENGTH = 64;
export const EXCLUDE_LIMIT_MESSAGE = "You can add up to 50 exclude words";
export const NO_DESCRIPTION_HINT = "Describe what you're looking for to start finding vacancies.";
export const SAVED_MESSAGE = "Saved";
export const DESCRIPTION_PLACEHOLDER =
  "Senior frontend, React or Vue, remote or EU, from 4000 €, no outsourcing";
export const EXCLUDE_HINT =
  "Posts containing any of these words or phrases are skipped. Press Enter or comma to add.";
