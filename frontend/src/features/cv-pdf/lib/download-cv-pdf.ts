import { createElement } from "react";
import type { Cv } from "@/entities/cv";

/**
 * Lazily imports @react-pdf/renderer and the CvDocument component,
 * renders the CV to a PDF blob, and triggers a browser download.
 * Lazy-loading keeps the heavy PDF library out of the main bundle.
 */
export async function downloadCvPdf(cv: Cv): Promise<void> {
  const [{ pdf }, { CvDocument }] = await Promise.all([
    import("@react-pdf/renderer"),
    import("../ui/cv-document"),
  ]);

  const element = createElement(CvDocument, { cv });
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- react-pdf types don't match React 18 exactly
  const blob = await pdf(element as any).toBlob();
  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.download = `${cv.name.replace(/[^a-zA-Z0-9-_ ]/g, "")}.pdf`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  URL.revokeObjectURL(url);
}
