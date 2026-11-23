# CV Upload Feature

"Upload CV" on the CVs page (spec 011, 2.3): one `.pdf`/`.docx` file → `POST /api/v1/cvs/upload` (extract only, creates nothing) → `/cvs/new` opens the text as an unsaved draft.

- `UploadCvButton`: hidden file input (`accept=".pdf,.docx"`, one file), "Uploading…" and `aria-disabled` (still focusable, `Button keepFocusable`; the click handler guards) while the request runs. A file over 5 MB is refused in the browser with the same text the server would give. On success it navigates (push) to `/cvs/new` with router state `{ uploadDraft: { name, content, truncated } }`.
- Errors come back as `{"detail": "<CODE>"}`; `lib/upload-error-message.ts` maps `UNSUPPORTED_FILE`, `FILE_TOO_LARGE`, `NO_TEXT`, `UPLOAD_FAILED` to the spec texts. Anything else (network, 401, 5xx, unknown code) shows the `UPLOAD_FAILED` text. Errors are shown as a toast.
- `useUploadDraft()` (used by `pages/cv-editor`): reads the draft from router state once into its own state, then clears the router state (`navigate(same URL, {replace: true, state: null})`). Browsers keep `history.state` across a reload, so the clear is what makes a reload open an empty new CV; the draft survives the replace because it lives in component state, and the editor's unsaved guard never blocks `REPLACE`.
- `UploadNotice({ truncated })`: presentational; "Text extracted from your file. Review it and save to add it to your CVs." plus the cut line. The page shows it while the draft is not saved.
- The file type is judged by the server from the content; `accept` only filters the picker.
