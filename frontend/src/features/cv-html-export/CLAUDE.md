# CV HTML Export Feature

"Download HTML" for a CV (backlog #11): a designed, standalone HTML file the user opens in a browser and prints to PDF. Appearance only: the text is laid out by `buildCvLayout` (`@/entities/cv`) and no word is ever added, removed or reordered (contact separators are shown as " · "). The react-pdf "Export PDF" (`features/cv-pdf`) is separate and unchanged.

- `downloadCvHtml({ name, content })` → "<name>.html" (`getCvHtmlFileName`, same rules as the PDF name), Blob `text/html;charset=utf-8`, via `triggerFileDownload` (`@/shared/lib`).
- `renderCvHtml(layout, { title, fontCss })` (`lib/render-cv-html.ts`) renders `CvLayoutView` with `renderToStaticMarkup`, so React escapes every text and attribute; only our constant CSS and the escaped `<title>` are concatenated by hand. A CSP `<meta>` (`default-src 'none'`) means the file can run no scripts and load nothing; links are http(s)/mailto only (`isSafeCvLinkUrl`, checked by the parser and again by the view).
- Lazy on purpose: `render-cv-html.ts` (pulls `react-dom/server`) and `cv-font-data-urls.ts` (~186 KB of base64 woff2 via Vite `?inline`) are dynamic imports inside `downloadCvHtml`. Do not export them from `index.ts` or import them statically; tests import `lib/render-cv-html` directly.
- A failed download shows `CV_HTML_DOWNLOAD_ERROR_MESSAGE` ("Couldn't create the file."), not the API network-error text: nothing goes over the network. The PDF keeps `handleApiError`.
- The editor preview shows the same view and stylesheet (`CvLayoutPreview` in `entities/cv`), so the preview is what gets downloaded.
