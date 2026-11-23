export type {
  Cv,
  CvCreate,
  CvUpdate,
  CvDuplicateRequest,
  CvUploadResult,
  CvKind,
  CvTailoredTarget,
} from "./model/types";

export { listCvs } from "./api/list-cvs";
export { createCv } from "./api/create-cv";
export { getCv } from "./api/get-cv";
export { updateCv } from "./api/update-cv";
export { deleteCv } from "./api/delete-cv";
export { duplicateCv } from "./api/duplicate-cv";
export { uploadCv } from "./api/upload-cv";
export { makeBaseCv } from "./api/make-base-cv";

export { parseCvMarkdown } from "./lib/cv-markdown";
export type { CvBlock, CvInline, CvListItem, CvHeadingLevel } from "./lib/cv-markdown";
export {
  groupCvs,
  isTailoredCv,
  getCvOptionLabel,
  buildCvSelectChoices,
  BASE_OPTION_SUFFIX,
  TAILORED_GROUP_LABEL,
} from "./lib/group-cvs";
export type { GroupedCvs, CvSelectChoices, CvSelectGroup, CvSelectOption } from "./lib/group-cvs";
export { formatTailoredFor, APPLICATION_DELETED_TEXT } from "./lib/tailored-for";
export { CvTextPreview } from "./ui/cv-text-preview";
export { CvTailoredFor } from "./ui/cv-tailored-for";
