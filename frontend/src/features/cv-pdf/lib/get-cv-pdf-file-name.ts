import { toSafeFileName } from "@/shared/lib";

/**
 * "<CV name>.pdf" with only invalid file-name characters replaced by "_".
 * Letters of any script (Cyrillic included), digits, spaces and punctuation
 * are kept; an empty or blank name falls back to "CV.pdf".
 */
export function getCvPdfFileName(name: string): string {
  return toSafeFileName(name, "pdf", "CV");
}
