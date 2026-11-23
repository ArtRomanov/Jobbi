# CV PDF Feature

"Export PDF" for a CV. `downloadCvTextPdf({ name, content })` renders the CV text with react-pdf and saves "<name>.pdf" (`getCvPdfFileName`: only `/ \ : * ? " < > |` and control characters become "_", Cyrillic kept, blank → "CV").

- `CvTextDocument` renders the block model from `parseCvMarkdown` (`@/entities/cv`), the same one the preview uses — never parse Markdown here. Empty text → only the CV name as a title; otherwise the name is not printed.
- Everything heavy is lazy: react-pdf, the document and `register-cv-fonts.ts` are dynamic imports inside `downloadCvTextPdf`. Do not import `ui/cv-text-document` or `lib/register-cv-fonts` statically from anywhere else, or the fonts and react-pdf land in the main chunk.
- Fonts: Noto Sans Regular/Bold/Italic/BoldItalic (Latin + Cyrillic) from `@/shared/assets/fonts` via Vite `?url`, OFL licence beside them. Hyphenation is turned off (words are never split).
