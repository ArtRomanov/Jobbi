import { z } from "zod";

export const registerSchema = z.object({
  full_name: z.string().min(1, "Full name is required"),
  email: z.string().email("Invalid email address"),
  password: z.string().min(8, "Password must be at least 8 characters"),
  desired_role: z.string().optional(),
  desired_location: z.string().optional(),
  remote_preference: z
    .enum(["onsite", "remote", "hybrid"])
    .optional(),
  salary_min: z.string().optional(),
  salary_max: z.string().optional(),
  salary_currency: z.string().optional(),
});

export type RegisterFormData = z.infer<typeof registerSchema>;
