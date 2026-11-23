import type { components } from "@/shared/api";

export type Cv = components["schemas"]["CvRead"];
export type CvCreate = components["schemas"]["CvCreate"];
export type CvUpdate = components["schemas"]["CvUpdate"];
export type CvDuplicateRequest = components["schemas"]["CvDuplicateRequest"];
export type CvUploadResult = components["schemas"]["CvUploadRead"];

/** Who a CV belongs to: the user's own CV, or a copy made by "Add & tailor CV". */
export type CvKind = Cv["kind"];

/** The application a tailored copy was made for. */
export type CvTailoredTarget = components["schemas"]["CvTailoredFor"];
