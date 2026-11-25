# CVs Page

Route page for `/cvs` (spec 011 §2.4–2.5). Composes `UploadCvButton` (`features/cv-upload`), `MakeBaseButton` (`features/cv-make-base`) `downloadCvTextPdf` (`features/cv-pdf`) and `downloadCvHtml` (`features/cv-html-export`).

- Sections come from `groupCvs` (`entities/cv`), keyed on `is_base` / `kind`, not on the server's order: "My CVs" (base first with a "Base" badge, then other own CVs) and "Tailored for applications" (hidden when empty; each row shows `CvTailoredFor` — "<Company> — <Role>" link to the dashboard panel, or "Application deleted").
- Row actions keep short visible text but have unique accessible names from `getCvActionLabel` (`lib/helpers.ts`): "Edit <name>" (a `ButtonLink`, never a button inside a link), "Duplicate <name>", "Export PDF: <name>" (text "PDF"), "Download HTML: <name>" (text "HTML"), "Delete <name>". PDF and HTML have separate loading states (`downloadingId`, `downloadingHtmlId`).
- No CVs at all → "No CVs yet. Upload your CV or create one." under "My CVs". At least one CV and no base → the no-base hint above "My CVs".
- The CV editor returns here (replace) after every successful save, with its save toast already shown by the root `ToastProvider`; the list is fetched on every mount, so the saved CV and its "Base" label are fresh.
- Toasts (spec 2.5): "CV duplicated", "CV deleted"; "Base CV updated" comes from `features/cv-make-base`.
- After delete / duplicate / make-base the list is refetched without the "Loading..." state, so rows do not flash. Each fetch is numbered (`latestRequestRef`); only the latest may set state, so a slow older response never overwrites a newer list. Only the first load shows its error in place of the list; a failed refresh keeps the list and shows a toast.
