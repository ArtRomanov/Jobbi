# CV Editor Page

Route page for `/cvs/new` and `/cvs/:id/edit`; composes `CvTextEditor` (`@/features/cv-text-editor`), loads/saves the CV and exports the saved version to PDF (`downloadCvTextPdf`).

- `cv` is the last saved/loaded CV; PATCH always sends its `version` and keeps the returned one.
- The editor is keyed by `editorSeed`, which changes only when a different CV loads. After "Create" the page navigates to `/cvs/<id>/edit` (replace); React Router keeps this page instance, so the editor and its draft stay mounted and the CV is not fetched again (`cvRef` already holds it).
