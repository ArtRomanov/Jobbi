/** Every character counts, including spaces and line breaks (functional spec 2.1). */
export const CV_CONTENT_MAX_LENGTH = 20_000;
export const CV_NAME_MAX_LENGTH = 255;

export const CV_NAME_REQUIRED_MESSAGE = "Required";
export const CV_FORMATTING_HINT = "# Heading · ## Section · **bold** · - list · [link](https://…)";
export const CV_CONTENT_PLACEHOLDER =
  "Write your CV here, or upload a PDF/DOCX on the CVs page.";

/** Phone width: editor and preview become the "Edit" / "Preview" tabs. */
export const PHONE_MEDIA_QUERY = "(max-width: 640px)";
