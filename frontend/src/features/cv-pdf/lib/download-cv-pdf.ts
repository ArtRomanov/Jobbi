import { createElement } from "react";
import type { Cv } from "@/entities/cv";
import { getCvPdfFileName } from "./get-cv-pdf-file-name";
import { triggerPdfDownload } from "./trigger-pdf-download";

/**
 * Legacy form-based CV export (still used by the CVs and CV editor pages).
 * Replaced by `downloadCvTextPdf({ name, content })` once the text editor
 * lands; delete together with `ui/cv-document.tsx` then.
 */
export async function downloadCvPdf(cv: Cv): Promise<void> {
  const [{ pdf }, { CvDocument }] = await Promise.all([
    import("@react-pdf/renderer"),
    import("../ui/cv-document"),
  ]);

  const element = createElement(CvDocument, { cv });
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- react-pdf types don't match React 18 exactly
  const blob = await pdf(element as any).toBlob();
  triggerPdfDownload(blob, getCvPdfFileName(cv.name));
}
