import type { VacancySourceKind } from "@/entities/vacancy-source";

/** Human label for each source kind, shown next to the source name. */
export const SOURCE_KIND_LABELS: Record<VacancySourceKind, string> = {
  telegram: "Telegram",
  greenhouse: "Greenhouse",
  lever: "Lever",
  lever_eu: "Lever",
  teamtailor: "Teamtailor",
  ashby: "Ashby",
  web: "Web page",
};

export const SCANNING_LABEL = "Scanning…";
export const UNAVAILABLE_LABEL = "Unavailable";
/** Shown after "Unavailable —" if the server sent no reason. */
export const UNAVAILABLE_FALLBACK_REASON = "Could not reach the source";
export const LAST_CHECKED_PREFIX = "Last checked";
/** Web page row before its first check after saving. */
export const WATCHING_SINCE_PREFIX = "Watching since";
/** How often the source list is re-fetched while any source is scanning. */
export const SCAN_POLL_INTERVAL_MS = 5000;
/** How often sources + status are re-fetched otherwise (only while the page is visible). */
export const STATUS_POLL_INTERVAL_MS = 60_000;
export const AI_UNAVAILABLE_NOTICE =
  "Vacancy search is temporarily unavailable — new posts will be checked when it's back";
export const LOAD_ERROR_MESSAGE = "Could not load your sources.";
export const NO_SOURCES_MESSAGE = "You are not watching any sources yet.";
export const SOURCE_INPUT_PLACEHOLDER =
  "@channel, t.me/channel, a job board or a job page link";
export const SOURCE_INPUT_LABEL = "Add a channel, job board or page";
export const ADD_BOARD_LABEL = "Add the board";
export const SOURCE_INPUT_HINT ="Sort the page by newest first before copying the link";

/** "Job link contains" (web pages): 1–100 characters when set. */
export const JOB_LINK_CONTAINS_MAX_LENGTH = 100;
export const JOB_LINK_CONTAINS_LABEL = "Job link contains";
export const JOB_LINK_CONTAINS_PLACEHOLDER = "/vacancy/";
export const SOURCE_NAME_MAX_LENGTH = 100;
export const SOURCE_NAME_LABEL = "Name";
export const FIELD_TOO_LONG_MESSAGE = "Use up to 100 characters";
/** How many vacancy titles the preview lists. */
export const PREVIEW_TITLES_LIMIT = 5;
/** Preview with no job links (only an ATS hint): same wording as the backend's 400. */
export const PREVIEW_NO_VACANCIES_TEXT =
  "No vacancies found on this page. Check the link or set 'Job link contains'.";

export const DESCRIPTION_MAX_LENGTH = 500;
export const NO_DESCRIPTION_HINT = "Describe what you're looking for to start finding vacancies.";
export const SAVED_MESSAGE = "Saved";
export const DESCRIPTION_PLACEHOLDER =
  "Senior frontend, React or Vue, remote or EU, from 4000 €, no outsourcing";
export const EDIT_SOURCE_TITLE = "Edit source";
export const EDIT_LABEL = "Edit";
export const SAVE_LABEL = "Save";
export const CANCEL_LABEL = "Cancel";
export const SOURCE_NAME_HINT = "Leave empty to use the default name";
export const SOURCE_LINK_LABEL = "Link";
export const LINK_REQUIRED_MESSAGE = "Enter a link";
/** Why Edit is disabled while a first-scan attempt runs. */
export const EDIT_UNAVAILABLE_HINT = "Scanning — try again in a moment";

/** Pre-AI keyword filter (the server checks the same limits and normalizes). */
export const KEYWORDS_MAX_COUNT = 50;
export const KEYWORD_MAX_LENGTH = 64;
export const KEYWORDS_LABEL = "Keywords";
export const KEYWORDS_PLACEHOLDER = "react, фронт, front end";
export const KEYWORDS_HINT =
  "Press Enter or a comma to add. A keyword also matches longer words (\"фронт\" finds \"фронтенд\"), and \"front end\" also finds \"front-end\".";
/** Same wording as the backend's 400. */
export const KEYWORDS_LIMIT_MESSAGE = "You can add up to 50 keywords";
export const KEYWORD_FILTER_LABEL = "Only send posts with these words to the AI";
export const KEYWORD_FILTER_HELP =
  "Skipped posts are deleted and don't come back if you change the keywords. Off or no keywords: every new post goes to the AI. Posts you forward to the bot are never skipped.";
export const FILTERED_LAST_24H_PREFIX = "Skipped by the filter in the last 24 hours:";
