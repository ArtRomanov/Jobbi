import type { components } from "@/shared/api";

/** Who a CV belongs to: the user's own CV, or a copy made by "Add & tailor CV". */
export type CvKind = "own" | "tailored";

/** The application a tailored copy was made for. */
export interface CvTailoredTarget {
  application_id: string;
  company_name: string;
  role_title: string;
}

/**
 * CvRead fields added by spec 011 slices 5–6 (base CV, tailored copies).
 *
 * TODO(011 integration): the backend for slices 5–6 is not merged yet, so the
 * generated `schema.d.ts` does not have these fields. Once it is regenerated,
 * delete this interface and the `& CvSlice56Fields` below (and `CvTailoredTarget`
 * if the schema names it) — the generated types then carry the same fields.
 */
interface CvSlice56Fields {
  is_base: boolean;
  kind: CvKind;
  tailored_for: CvTailoredTarget | null;
  /** The tailored copy's application was deleted: show "Application deleted". */
  tailored_application_deleted: boolean;
}

export type Cv = components["schemas"]["CvRead"] & CvSlice56Fields;
export type CvCreate = components["schemas"]["CvCreate"];
export type CvUpdate = components["schemas"]["CvUpdate"];
export type CvDuplicateRequest = components["schemas"]["CvDuplicateRequest"];
export type CvUploadResult = components["schemas"]["CvUploadRead"] & CvSlice56Fields;
