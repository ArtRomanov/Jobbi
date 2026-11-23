import type { Cv } from "../model/types";

/** A CV list split the way the CVs page and every CV select show it. */
export interface GroupedCvs {
  /** The base CV, or null when the user has none. */
  base: Cv | null;
  /** Own CVs: the base first, then the rest by `updated_at` desc. */
  own: Cv[];
  /** Tailored copies by `updated_at` desc. */
  tailored: Cv[];
}

export interface CvSelectOption {
  value: string;
  label: string;
}

export interface CvSelectGroup {
  label: string;
  options: CvSelectOption[];
}

/** `<select>` content: own CVs as plain options, tailored copies as one optgroup. */
export interface CvSelectChoices {
  options: CvSelectOption[];
  groups: CvSelectGroup[];
}

export const BASE_OPTION_SUFFIX = " (base)";
export const TAILORED_GROUP_LABEL = "Tailored copies";

/** A tailored copy that is not the base (a base is always shown as own, whatever `kind` says). */
export function isTailoredCv(cv: Cv): boolean {
  return cv.kind === "tailored" && !cv.is_base;
}

function byUpdatedDesc(a: Cv, b: Cv): number {
  // ISO timestamps from the API compare as strings
  if (a.updated_at === b.updated_at) return 0;
  return a.updated_at > b.updated_at ? -1 : 1;
}

/**
 * Groups CVs by `is_base` / `kind`. The server already sends them in this
 * order; the grouping and sort are repeated so the UI does not depend on it.
 */
export function groupCvs(cvs: readonly Cv[]): GroupedCvs {
  let base: Cv | null = null;
  const otherOwn: Cv[] = [];
  const tailored: Cv[] = [];
  for (const cv of cvs) {
    if (cv.is_base && base === null) base = cv;
    else if (isTailoredCv(cv)) tailored.push(cv);
    else otherOwn.push(cv);
  }
  otherOwn.sort(byUpdatedDesc);
  tailored.sort(byUpdatedDesc);
  return { base, own: base ? [base, ...otherOwn] : otherOwn, tailored };
}

/** Option label: the base is marked "(base)". */
export function getCvOptionLabel(cv: Cv): string {
  return cv.is_base ? `${cv.name}${BASE_OPTION_SUFFIX}` : cv.name;
}

/** Own CVs first (base first, "(base)"), then a "Tailored copies" group if there are any. */
export function buildCvSelectChoices(cvs: readonly Cv[]): CvSelectChoices {
  const { own, tailored } = groupCvs(cvs);
  const toOption = (cv: Cv): CvSelectOption => ({ value: cv.id, label: getCvOptionLabel(cv) });
  return {
    options: own.map(toOption),
    groups:
      tailored.length > 0 ? [{ label: TAILORED_GROUP_LABEL, options: tailored.map(toOption) }] : [],
  };
}
