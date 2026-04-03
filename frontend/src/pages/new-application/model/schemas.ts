import { z } from "zod";

export const newApplicationSchema = z.object({
  company_name: z.string().min(1, "Company name is required"),
  role_title: z.string().min(1, "Role title is required"),
  job_url: z.string().optional(),
  salary_min: z.string().optional(),
  salary_max: z.string().optional(),
  salary_currency: z.string().optional(),
  contact_name: z.string().optional(),
  contact_email: z.string().optional(),
  notes: z.string().optional(),
  status: z.enum(["researching", "applied", "interview", "offer", "rejected", "withdrawn"]),
});

export type NewApplicationFormData = z.infer<typeof newApplicationSchema>;
