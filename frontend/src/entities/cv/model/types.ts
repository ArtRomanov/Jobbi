import type { components } from "@/shared/api";

export type Cv = components["schemas"]["CvRead"];
export type CvDuplicateRequest = components["schemas"]["CvDuplicateRequest"];

// TODO(spec 011 slice 9): the backend contract below lands on a parallel
// branch. After it merges, regenerate `schema.d.ts` and alias these to the
// generated `CvCreate` / `CvUpdate` / upload-response schemas.

/**
 * `POST /cvs` body. `is_base: true` makes the new CV the base (the previous
 * base becomes an ordinary own CV); omitted or false leaves the base alone.
 */
export interface CvCreate {
  name: string;
  content: string;
  is_base?: boolean;
}

/**
 * `PATCH /cvs/{id}` body. `is_base: true` makes this CV the base; `false`
 * clears the base only when this CV is the current base. Omitted = unchanged.
 */
export interface CvUpdate {
  name?: string | null;
  content?: string | null;
  version: number;
  is_base?: boolean;
}

/**
 * `POST /cvs/upload` response: the extracted text only. Nothing is created
 * until the user saves the draft (spec 011 §2.3).
 */
export interface CvUploadResult {
  /** The file name without its extension, cut to 255 ("Uploaded CV" if empty). */
  name: string;
  content: string;
  /** The text was longer than 20 000 characters and was cut. */
  truncated: boolean;
}

/** Who a CV belongs to: the user's own CV, or a copy made by "Add & tailor CV". */
export type CvKind = Cv["kind"];

/** The application a tailored copy was made for. */
export type CvTailoredTarget = components["schemas"]["CvTailoredFor"];
