import { z } from "zod";

const personalInfoSchema = z.object({
  full_name: z.string(),
  email: z.string(),
  phone: z.string(),
  location: z.string(),
  linkedin_url: z.string(),
});

const workExperienceSchema = z.object({
  company: z.string().min(1, "Company is required"),
  role: z.string().min(1, "Role is required"),
  start_date: z.string(),
  end_date: z.string(),
  is_current: z.boolean(),
  description: z.string(),
});

const educationSchema = z.object({
  institution: z.string().min(1, "Institution is required"),
  degree: z.string(),
  field_of_study: z.string(),
  start_year: z.string(),
  end_year: z.string(),
  description: z.string(),
});

export const cvFormSchema = z.object({
  name: z.string().min(1, "CV name is required"),
  personal_info: personalInfoSchema,
  summary: z.string(),
  work_experience: z.array(workExperienceSchema),
  education: z.array(educationSchema),
  skills: z.string(),
  languages: z.string(),
});

export type CvFormValues = z.infer<typeof cvFormSchema>;
