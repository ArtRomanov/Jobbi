import type { CvTailoredTarget } from "../model/types";

export const APPLICATION_DELETED_TEXT = "Application deleted";

/** "<Company> — <Role>"; an empty part is left out. */
export function formatTailoredFor({ company_name, role_title }: CvTailoredTarget): string {
  return [company_name.trim(), role_title.trim()].filter((part) => part !== "").join(" — ");
}
