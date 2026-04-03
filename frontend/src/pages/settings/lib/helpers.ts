import type { User } from "@/entities/user";
import type { SettingsFormData } from "../model/schemas";

/** Convert user API data to form field values. */
export function userToFormValues(user: User): SettingsFormData {
  return {
    full_name: user.full_name,
    desired_role: user.desired_role ?? "",
    desired_location: user.desired_location ?? "",
    remote_preference: (user.remote_preference as SettingsFormData["remote_preference"]) ?? "",
    salary_min: user.salary_min !== null ? String(user.salary_min) : "",
    salary_max: user.salary_max !== null ? String(user.salary_max) : "",
    salary_currency: user.salary_currency ?? "",
  };
}
