import type { CSSProperties } from "react";
import { colors } from "@/shared/ui";

/** Every character counts, including spaces and line breaks (functional spec 2.1). */
export const CV_CONTENT_MAX_LENGTH = 20_000;
export const CV_NAME_MAX_LENGTH = 255;

export const CV_NAME_REQUIRED_MESSAGE = "Required";
export const CV_FORMATTING_HINT = "# Heading · ## Section · **bold** · - list · [link](https://…)";
/** What screen readers get instead of the symbols in `CV_FORMATTING_HINT`. */
export const CV_FORMATTING_HINT_DESCRIPTION =
  "Formatting: start a line with # for a heading, ## for a section, wrap text in two asterisks for bold, start a line with a dash for a list item, write links as text in square brackets followed by the address in parentheses.";
export const CV_CONTENT_PLACEHOLDER =
  "Write your CV here, or upload a PDF/DOCX on the CVs page.";

/**
 * Fixed height of the CV text box and the preview box. Both scroll inside
 * themselves instead of growing the page, so they stay a matching pair.
 */
export const CV_PANE_HEIGHT = "32rem";

/**
 * The box shared by the CV textarea and the preview: same height, border,
 * padding and background, its own vertical scroll.
 */
export const CV_PANE_BOX_STYLE = {
  height: CV_PANE_HEIGHT,
  overflowY: "auto",
  padding: "0.5rem 0.75rem",
  border: `1px solid ${colors.border}`,
  borderRadius: "0.375rem",
  backgroundColor: colors.bgCard,
  boxSizing: "border-box",
} as const satisfies CSSProperties;

/** Phone width: editor and preview become the "Edit" / "Preview" tabs. */
export const PHONE_MEDIA_QUERY = "(max-width: 640px)";

/** The "N / 20 000" counter shows once the text is longer than this. */
export const CV_CONTENT_COUNTER_THRESHOLD = 18_000;

export const CV_SAVE_FAILED_MESSAGE = "Could not save the CV. Please try again.";
export const CV_CHANGED_ELSEWHERE_MESSAGE =
  "This CV was changed elsewhere (for example in the AI chat). Reload to see the latest version.";
/** `detail` of the PATCH 409 when the sent `version` is stale. */
export const CV_CHANGED_ERROR_CODE = "CV_CHANGED";

export const BASE_CV_SWITCH_LABEL = "Base CV";
/** Straight quotes, like the CVs page's no-base hint. */
export const BASE_CV_SWITCH_HELP = 'Tailoring with "Add & tailor CV" starts from your base CV.';

export const UNSAVED_CHANGES_MESSAGE = "You have unsaved changes. Leave without saving?";
export const UNSAVED_CHANGES_LEAVE_LABEL = "Leave";
export const UNSAVED_CHANGES_STAY_LABEL = "Stay";
