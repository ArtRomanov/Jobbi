# CV Upload Feature

"Upload CV" on the CVs page (spec 011, 2.3): one `.pdf`/`.docx` file → `POST /api/v1/cvs/upload` → new own CV → its editor opens.

- `UploadCvButton`: hidden file input (`accept=".pdf,.docx"`, one file), "Uploading…" and `aria-disabled` (still focusable, `Button keepFocusable`; the click handler guards) while the request runs. A file over 5 MB is refused in the browser with the same text the server would give. On success it navigates to `/cvs/<id>/edit` with router state `{ uploadNotice: { truncated, becameBase } }`.
- Errors come back as `{"detail": "<CODE>"}`; `lib/upload-error-message.ts` maps `UNSUPPORTED_FILE`, `FILE_TOO_LARGE`, `NO_TEXT`, `UPLOAD_FAILED` to the spec texts. Anything else (network, 401, 5xx, unknown code) shows the `UPLOAD_FAILED` text. Errors are shown as a toast.
- `UploadNotice`: mount it in the CV editor page. It reads the router state and shows "Text extracted from your file. Check the line breaks and save." plus the cut / base lines; without that state it renders nothing. It keeps the notice in component state and clears the router state at once (`navigate(same URL, {replace: true, state: null})`), so a reload or history visit does not show it again. Mounted by `pages/cv-editor`.
- The file type is judged by the server from the content; `accept` only filters the picker.
