import { createElement } from "react";
import type { CvTextDocumentProps } from "../ui/cv-text-document";
import { getCvPdfFileName } from "./get-cv-pdf-file-name";
import { triggerFileDownload } from "@/shared/lib";

export type CvPdfSource = CvTextDocumentProps;

/**
 * Renders a CV text to PDF and downloads it as "<name>.pdf". react-pdf, the
 * document and the Noto Sans fonts are all imported lazily, so none of them
 * reach the main bundle.
 */
export async function downloadCvTextPdf({ name, content }: CvPdfSource): Promise<void> {
  const [{ pdf }, { CvTextDocument }, { registerCvFonts }] = await Promise.all([
    import("@react-pdf/renderer"),
    import("../ui/cv-text-document"),
    import("./register-cv-fonts"),
  ]);
  registerCvFonts();

  const element = createElement(CvTextDocument, { name, content });
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- react-pdf types don't match React 18 exactly
  const blob = await pdf(element as any).toBlob();
  triggerFileDownload(blob, getCvPdfFileName(name));
}
