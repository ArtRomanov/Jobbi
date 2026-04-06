import type { CvFormValues } from "../model/schemas";

export const EMPTY_WORK_EXPERIENCE: CvFormValues["work_experience"][number] = {
  company: "",
  role: "",
  start_date: "",
  end_date: "",
  is_current: false,
  description: "",
};

export const EMPTY_EDUCATION: CvFormValues["education"][number] = {
  institution: "",
  degree: "",
  field_of_study: "",
  start_year: "",
  end_year: "",
  description: "",
};
