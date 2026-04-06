import type { components } from "@/shared/api";

export type Cv = components["schemas"]["CvRead"];
export type CvCreate = components["schemas"]["CvCreate"];
export type CvUpdate = components["schemas"]["CvUpdate"];
export type PersonalInfo = components["schemas"]["PersonalInfo"];
export type WorkExperienceEntry = components["schemas"]["WorkExperienceEntry"];
export type EducationEntry = components["schemas"]["EducationEntry"];
export type CvDuplicateRequest = components["schemas"]["CvDuplicateRequest"];
