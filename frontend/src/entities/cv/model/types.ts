import type { components } from "@/shared/api";

export type Cv = components["schemas"]["CvRead"];
/**
 * `POST /cvs` body. `is_base: true` makes the new CV the base (the previous
 * base becomes an ordinary own CV); false leaves the base alone.
 */
export type CvCreate = components["schemas"]["CvCreate"];
/**
 * `PATCH /cvs/{id}` body. `is_base: true` makes this CV the base; `false`
 * clears the base only when this CV is the current base; omitted = unchanged.
 */
export type CvUpdate = components["schemas"]["CvUpdate"];
export type CvDuplicateRequest = components["schemas"]["CvDuplicateRequest"];
/**
 * `POST /cvs/upload` response: the extracted text only. Nothing is created
 * until the user saves the draft (spec 011 §2.3).
 */
export type CvUploadResult = components["schemas"]["CvExtractRead"];

/** Who a CV belongs to: the user's own CV, or a copy made by "Add & tailor CV". */
export type CvKind = Cv["kind"];

/** The application a tailored copy was made for. */
export type CvTailoredTarget = components["schemas"]["CvTailoredFor"];
