import { z } from "zod";
import {
  FIELD_TOO_LONG_MESSAGE,
  JOB_LINK_CONTAINS_MAX_LENGTH,
  SOURCE_NAME_MAX_LENGTH,
} from "../lib/constants";
import type { WebSourceFieldErrors } from "./types";

/** Trimmed optional text: empty → null (the server then uses its default). */
function optionalText(maxLength: number) {
  return z
    .string()
    .trim()
    .max(maxLength, FIELD_TOO_LONG_MESSAGE)
    .transform((value) => (value === "" ? null : value));
}

/** "Job link contains" (1–100 when set) and the optional name (≤ 100) of a web page source. */
export const webSourceOptionsSchema = z.object({
  jobLinkContains: optionalText(JOB_LINK_CONTAINS_MAX_LENGTH),
  name: optionalText(SOURCE_NAME_MAX_LENGTH),
});

export type WebSourceOptions = z.output<typeof webSourceOptionsSchema>;

/** Per-field messages: the first issue of each known field wins, other paths are ignored. */
export function toFieldErrors(
  issues: readonly Pick<z.core.$ZodIssue, "path" | "message">[],
): WebSourceFieldErrors {
  const errors: WebSourceFieldErrors = {};
  for (const issue of issues) {
    const field = issue.path[0];
    if (field === "jobLinkContains" || field === "name") errors[field] ??= issue.message;
  }
  return errors;
}
