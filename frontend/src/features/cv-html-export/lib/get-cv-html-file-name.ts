import { toSafeFileName } from "@/shared/lib";

/** "<CV name>.html"; invalid file-name characters become "_", blank → "CV.html". */
export function getCvHtmlFileName(name: string): string {
  return toSafeFileName(name, "html", "CV");
}
