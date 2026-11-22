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
