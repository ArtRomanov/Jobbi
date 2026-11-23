# CV Entity

CV types (aliases of the generated OpenAPI schemas), CRUD API functions, and the CV text formatting shared by the preview and the PDF.

- `parseCvMarkdown(content)` (`lib/cv-markdown.ts`) is the ONE place CV Markdown is parsed: a `marked` lexer (GFM, `breaks: true`) walked into a renderer-neutral block model (`CvBlock` / `CvInline`). Supported: heading 1–3, paragraph, bold, italic, bullet/ordered lists, links, line breaks. Everything else (tables, HTML, images, code, quotes, rules, heading 4+) becomes a `raw` block / text with the token's `raw`, i.e. shown exactly as typed. `features/cv-pdf` renders the same model — add formatting here, never in one renderer only.
- Reference definitions (`[1]: https://…`) are not printed. Display text decodes only `&amp; &lt; &gt; &quot;` and numeric entities; `raw` text is kept as typed.
- Links: only `isSafeCvLinkUrl` (http, https, mailto) becomes a `link` node; any other link is kept as its typed text. The check runs on the href as typed, never entity-decoded (`&#106;avascript:` stays unsafe). Renderers re-check it.
- `CvTextPreview` renders React elements only (no `dangerouslySetInnerHTML`); headings 1–3 map to `h2`–`h4` because the host page owns the `h1`.
