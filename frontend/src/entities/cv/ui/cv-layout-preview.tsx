import { memo, useMemo } from "react";
import { CV_FONT_URLS } from "../lib/cv-font-urls";
import { buildCvFontFaceCss } from "../lib/cv-layout-fonts";
import { buildCvLayout } from "../lib/cv-layout";
import { CV_LAYOUT_CSS } from "../lib/cv-layout-styles";
import { CvLayoutView } from "./cv-layout-view";

interface CvLayoutPreviewProps {
  /** The CV text (simple Markdown). */
  content: string;
}

// Our own constant CSS (fonts by asset URL + the shared CV stylesheet); no CV
// text ever goes into it. React sets it as the <style> element's text.
const PREVIEW_CSS = `${buildCvFontFaceCss(CV_FONT_URLS)}\n${CV_LAYOUT_CSS}`;

/**
 * The designed CV inside an app page (editor preview): the same view and the
 * same stylesheet as "Download HTML", so what the user sees is what they get.
 */
export const CvLayoutPreview = memo(function CvLayoutPreview({ content }: CvLayoutPreviewProps) {
  const layout = useMemo(() => buildCvLayout(content), [content]);
  return (
    <>
      <style>{PREVIEW_CSS}</style>
      <CvLayoutView layout={layout} isEmbedded />
    </>
  );
});
