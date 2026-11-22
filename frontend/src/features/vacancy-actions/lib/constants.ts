/** How long "Dismissed · Undo" stays and Undo is possible (functional spec 2.3). */
export const UNDO_WINDOW_MS = 5000;
export const DISMISSED_MESSAGE = "Dismissed";
export const UNDO_LABEL = "Undo";
export const OPEN_SOURCE_LABEL = "Open source";
export const DISMISS_LABEL = "Dismiss";
export const UNSAFE_URL_HINT = "This link cannot be opened";
export const RESTORE_ERROR_MESSAGE = "Could not undo. The vacancy stays dismissed.";
/** `window.open` features: the new tab gets no `window.opener` and no referrer. */
export const NEW_TAB_FEATURES = "noopener,noreferrer";

// --- Add to tracker (functional spec 2.3) ---
export const ADD_TO_TRACKER_LABEL = "Add to tracker";
export const ADD_AND_TAILOR_LABEL = "Add & tailor CV";
export const ADD_DIALOG_TITLE = "Add to tracker";
export const CANCEL_LABEL = "Cancel";
export const REQUIRED_MESSAGE = "Required";
/** `applications.company_name` / `role_title` length on the server. */
export const MAX_NAME_LENGTH = 255;
export const TOO_LONG_MESSAGE = `Must be ${MAX_NAME_LENGTH} characters or fewer`;
export const ADD_ERROR_MESSAGE = "Could not add this vacancy. Please try again.";
/** Statuses whose string `detail` is clearer than the generic message ("CV not found.", "Already added"…). */
export const SPECIFIC_ERROR_STATUSES: ReadonlySet<number> = new Set([404, 409]);
/** Server `detail` of the 409 when the card is already added (e.g. from another tab). */
export const ALREADY_ADDED_DETAIL = "Already added";
export const ALREADY_ADDED_MESSAGE = "Already in your tracker";
export const ADDED_MESSAGE = "Added to tracker";
export const OPEN_APPLICATION_LABEL = "Open application";
/** Longer than the 3 s default: the toast carries a link. It also pauses on hover/focus. */
export const ADDED_TOAST_DURATION_MS = 8000;
export const DUPLICATE_PREFIX = "You already track this:";
export const OPEN_EXISTING_LABEL = "Open it";
export const ADD_ANYWAY_LABEL = "Add anyway";
export const BASE_CV_LABEL = "Base CV";
export const NO_CVS_HINT = "Create a CV first";
export const CVS_LOAD_ERROR_HINT = "Could not load your CVs.";
export const CVS_LOADING_HINT = "Loading your CVs…";
/** First chat message after "Add & tailor CV"; pre-filled, sent only by the user. */
export const TAILOR_CV_DRAFT = "Adapt my CV to this vacancy";
