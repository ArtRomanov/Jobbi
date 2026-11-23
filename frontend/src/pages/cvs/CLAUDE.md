# CVs Page

Route page for `/cvs` (spec 011 §2.4–2.5). Composes `UploadCvButton` (`features/cv-upload`), `MakeBaseButton` (`features/cv-make-base`) and `downloadCvTextPdf` (`features/cv-pdf`).

- Sections come from `groupCvs` (`entities/cv`), keyed on `is_base` / `kind`, not on the server's order: "My CVs" (base first with a "Base" badge, then other own CVs) and "Tailored for applications" (hidden when empty; each row shows `CvTailoredFor` — "<Company> — <Role>" link to the dashboard panel, or "Application deleted").
- No CVs at all → "No CVs yet. Upload your CV or create one." under "My CVs". At least one CV and no base → the no-base hint above "My CVs".
- After delete / duplicate / make-base the list is refetched without the "Loading..." state, so rows do not flash.
