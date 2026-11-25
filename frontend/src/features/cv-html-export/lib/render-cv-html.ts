import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { CV_LAYOUT_CSS, CvLayoutView, type CvLayout } from "@/entities/cv";

export interface RenderCvHtmlOptions {
  /** The document `<title>` (the CV name); escaped here. */
  title: string;
  /** `@font-face` rules (our own, from `buildCvFontFaceCss`); none → system fallbacks. */
  fontCss?: string;
}

const HTML_ESCAPES: Readonly<Record<string, string>> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

/** Escapes text for HTML text and attribute contexts. */
export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (char) => HTML_ESCAPES[char] ?? char);
}

// Defence in depth: the file never runs scripts, loads nothing from the
// network and cannot be framed into a form. Fonts and styles are inline.
const CONTENT_SECURITY_POLICY =
  "default-src 'none'; style-src 'unsafe-inline'; font-src data:; img-src data:; base-uri 'none'; form-action 'none'";

// Page setup for print and the A4 "sheet" look on screen. Our own constant CSS.
const PAGE_CSS = `
@page{size:A4;margin:12mm 15mm}
html{background:#fff}
body{margin:0;background:#fff}
@media screen{
  html,body{background:#E9ECEF}
  body{padding:24px 0}
  .cv-sheet{box-sizing:border-box;width:210mm;min-height:297mm;margin:0 auto;padding:12mm 15mm;background:#fff;box-shadow:0 1px 4px rgba(0,0,0,.18)}
}
@media screen and (max-width:220mm){
  body{padding:0}
  .cv-sheet{width:auto;min-height:0;padding:16px;box-shadow:none}
}
@media print{
  html,body{background:#fff}
  .cv-sheet{width:auto;min-height:0;margin:0;padding:0;box-shadow:none}
}
`;

/**
 * A complete standalone HTML document of the designed CV ("Download HTML",
 * backlog #11): A4 print layout, inline CSS and fonts, no scripts. The body is
 * rendered by React (`CvLayoutView`), so every piece of CV text and every
 * attribute is escaped; the only strings put in by hand are our own CSS and
 * the escaped title.
 */
export function renderCvHtml(layout: CvLayout, { title, fontCss = "" }: RenderCvHtmlOptions): string {
  const body = renderToStaticMarkup(createElement(CvLayoutView, { layout, isEmbedded: false }));
  // Our CSS never contains "</style", but make sure it cannot end the element
  const css = `${fontCss}\n${PAGE_CSS}\n${CV_LAYOUT_CSS}`.replace(/<\/style/gi, "<\\/style");
  return [
    "<!DOCTYPE html>",
    "<html>",
    "<head>",
    '<meta charset="utf-8">',
    `<meta http-equiv="Content-Security-Policy" content="${CONTENT_SECURITY_POLICY}">`,
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    `<title>${escapeHtml(title)}</title>`,
    `<style>${css}</style>`,
    "</head>",
    "<body>",
    `<main class="cv-sheet">${body}</main>`,
    "</body>",
    "</html>",
    "",
  ].join("\n");
}
