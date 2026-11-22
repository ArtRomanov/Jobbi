import type { VacancyCardSource } from "../model/types";
import { POSTED_IN_LABEL, VACANCY_PREVIEW_LENGTH } from "./constants";

interface TextPreview {
  /** First 300 characters (with "…" when cut), or the whole text. */
  preview: string;
  isTruncated: boolean;
}

/** Cut the card text to the preview length; short texts come back whole. */
export function getTextPreview(text: string): TextPreview {
  if (text.length <= VACANCY_PREVIEW_LENGTH) return { preview: text, isTruncated: false };
  return { preview: `${text.slice(0, VACANCY_PREVIEW_LENGTH).trimEnd()}…`, isTruncated: true };
}

/** Card source line: "@a" for one source, "Posted in: @a, @b" for merged reposts. */
export function formatCardSources(sources: readonly VacancyCardSource[]): string {
  const labels = sources.map((source) => source.label).join(", ");
  return sources.length > 1 ? `${POSTED_IN_LABEL} ${labels}` : labels;
}
