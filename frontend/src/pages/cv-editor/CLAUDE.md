# CV Editor Page

Route page for `/cvs/new` and `/cvs/:id/edit`; composes `CvTextEditor` (`@/features/cv-text-editor`), loads/saves the CV and, in edit mode, passes `onExport` so the editor's current draft goes to `downloadCvTextPdf`.
- A ref (`isSavingRef`) drops a second Save while one is in flight.

- `cv` is the last saved/loaded CV; PATCH always sends its `version` and keeps the returned one.
- The editor is keyed by `editorSeed`, which changes only when a different CV loads. After "Create" the page navigates to `/cvs/<id>/edit` (replace); React Router keeps this page instance, so the editor and its draft stay mounted and the CV is not fetched again (`cvRef` already holds it). `cv` state and `cvRef` change together, only via `setSavedCv`.
- `UploadNotice` (`@/features/cv-upload`) sits above the editor: right after an upload it shows the extracted-text notice from router state, then clears that state (replace, same URL) so a reload does not show it again.
