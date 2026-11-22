import type { BadgeTone } from "@/shared/ui";
import type { VacancyFit } from "../model/types";

/** Characters of post text shown before "Show more". */
export const VACANCY_PREVIEW_LENGTH = 300;

export const UNKNOWN_ROLE = "Unknown role";
export const UNKNOWN_COMPANY = "Unknown company";
export const NEW_LABEL = "New";
/** Screen-reader prefix of the fit badge, so "High" is read as "Fit: High". */
export const FIT_PREFIX = "Fit:";
export const SHOW_MORE_LABEL = "Show more";
export const SHOW_LESS_LABEL = "Show less";
/** Prefix of the source line when reposts were merged into one card. */
export const POSTED_IN_LABEL = "Posted in:";

export const FIT_LABELS: Record<VacancyFit, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

export const FIT_TONES: Record<VacancyFit, BadgeTone> = {
  high: "success",
  medium: "warning",
  low: "danger",
};
