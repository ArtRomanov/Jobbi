import { STATUSES } from "@/entities/application";

export const STATUS_OPTIONS = STATUSES.map((s) => ({ value: s.key, label: s.label }));

/** Load error for an id that does not exist (or is not the user's), e.g. a stale deep link. */
export const APPLICATION_NOT_FOUND_MESSAGE = "Application not found";
export const APPLICATION_LOAD_ERROR_MESSAGE = "Failed to load application";
