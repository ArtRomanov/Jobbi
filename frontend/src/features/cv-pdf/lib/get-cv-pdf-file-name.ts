// Characters Windows/macOS/Linux refuse in file names, plus C0 controls and DEL.
const INVALID_FILE_NAME_CHARS = /[/\\:*?"<>|\u0000-\u001f\u007f]/g;
const FALLBACK_NAME = "CV";

/**
 * "<CV name>.pdf" with only invalid file-name characters replaced by "_".
 * Letters of any script (Cyrillic included), digits, spaces and punctuation
 * are kept; an empty or blank name falls back to "CV.pdf".
 */
export function getCvPdfFileName(name: string): string {
  const safe = name.replace(INVALID_FILE_NAME_CHARS, "_").trim();
  return `${safe === "" ? FALLBACK_NAME : safe}.pdf`;
}
