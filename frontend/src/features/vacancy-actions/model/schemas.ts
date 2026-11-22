import { z } from "zod";
import { MAX_NAME_LENGTH, REQUIRED_MESSAGE, TOO_LONG_MESSAGE } from "../lib/constants";

const requiredName = z
  .string()
  .trim()
  .min(1, REQUIRED_MESSAGE)
  .max(MAX_NAME_LENGTH, TOO_LONG_MESSAGE);

/** "Add to tracker" dialog. `base_cv_id` is "" when the user has no CVs. */
export const addToTrackerSchema = z.object({
  company_name: requiredName,
  role_title: requiredName,
  notes: z.string(),
  base_cv_id: z.string(),
});

export type AddToTrackerFormValues = z.infer<typeof addToTrackerSchema>;
