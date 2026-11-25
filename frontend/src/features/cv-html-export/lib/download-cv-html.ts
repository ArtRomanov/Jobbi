import { buildCvFontFaceCss, buildCvLayout } from "@/entities/cv";
import { triggerFileDownload } from "@/shared/lib";
import { getCvHtmlFileName } from "./get-cv-html-file-name";

export interface CvHtmlSource {
  name: string;
  content: string;
}

/** Title used when the CV name is blank (matches the file-name fallback). */
const FALLBACK_TITLE = "CV";

/**
 * Builds the designed HTML of a CV and downloads it as "<name>.html", for the
 * user to open in a browser and print to PDF. `react-dom/server` and the
 * base64 fonts are imported lazily, so neither reaches the main bundle.
 */
export async function downloadCvHtml({ name, content }: CvHtmlSource): Promise<void> {
  const [{ renderCvHtml }, { CV_FONT_DATA_URLS }] = await Promise.all([
    import("./render-cv-html"),
    import("./cv-font-data-urls"),
  ]);
  const html = renderCvHtml(buildCvLayout(content), {
    title: name.trim() === "" ? FALLBACK_TITLE : name.trim(),
    fontCss: buildCvFontFaceCss(CV_FONT_DATA_URLS),
  });
  triggerFileDownload(new Blob([html], { type: "text/html;charset=utf-8" }), getCvHtmlFileName(name));
}
