/** Every character counts, including spaces and line breaks (functional spec 2.1). */
export const CV_CONTENT_MAX_LENGTH = 20_000;
export const CV_NAME_MAX_LENGTH = 255;

export const CV_NAME_REQUIRED_MESSAGE = "Required";
export const CV_FORMATTING_HINT = "# Heading · ## Section · **bold** · - list · [link](https://…)";
export const CV_CONTENT_PLACEHOLDER =
  "Write your CV here, or upload a PDF/DOCX on the CVs page.";

/** Phone width: editor and preview become the "Edit" / "Preview" tabs. */
export const PHONE_MEDIA_QUERY = "(max-width: 640px)";

/** The "N / 20 000" counter shows once the text is longer than this. */
export const CV_CONTENT_COUNTER_THRESHOLD = 18_000;

export const CV_SAVE_FAILED_MESSAGE = "Could not save the CV. Please try again.";
export const CV_CHANGED_ELSEWHERE_MESSAGE =
  "This CV was changed elsewhere (for example in the AI chat). Reload to see the latest version.";
/** `detail` of the PATCH 409 when the sent `version` is stale. */
export const CV_CHANGED_ERROR_CODE = "CV_CHANGED";

export const UNSAVED_CHANGES_MESSAGE = "You have unsaved changes. Leave without saving?";
export const UNSAVED_CHANGES_LEAVE_LABEL = "Leave";
export const UNSAVED_CHANGES_STAY_LABEL = "Stay";
