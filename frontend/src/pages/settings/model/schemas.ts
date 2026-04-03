import { z } from "zod";

export const settingsSchema = z.object({
  full_name: z.string().min(1, "Full name is required"),
  desired_role: z.string().optional(),
  desired_location: z.string().optional(),
  remote_preference: z.enum(["onsite", "remote", "hybrid", ""]).optional(),
  salary_min: z.string().optional(),
  salary_max: z.string().optional(),
  salary_currency: z.string().optional(),
});

export type SettingsFormData = z.infer<typeof settingsSchema>;

export const changePasswordSchema = z.object({
  current_password: z.string().min(1, "Current password is required"),
  new_password: z.string().min(8, "New password must be at least 8 characters"),
});

export type ChangePasswordFormData = z.infer<typeof changePasswordSchema>;
