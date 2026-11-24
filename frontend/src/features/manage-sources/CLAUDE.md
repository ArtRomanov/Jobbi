# Manage Sources Feature

Inbox "Sources" panel (`SourcesPanel`): add a Telegram channel by `@name` / `t.me/name`, list watched sources with "Scanning…" / "Unavailable" + reason, remove a source (no confirm), and the "What are you looking for?" form (search description only — exclude words are hidden since spec 012).

- State lives in `model/use-manage-sources.ts`. Add errors are shown inline under the input (`getErrorMessage` — the backend's 400/409 `detail` text is user-facing); remove errors go to a toast.
- The add form stays disabled until the initial list loads, so a late GET can't overwrite a just-added source.
- Focus: after Add (success or error) it returns to the input; after Remove it moves to the next Remove button, else the previous one, else the input (`lib/helpers.ts`).
- The backend checks a channel live (up to ~10 s), so the input is read-only and "Add" shows loading while a request runs; a ref blocks double submits.
- Search settings: `SearchSettingsForm` + `model/use-search-settings-form.ts`. Saved settings come from the same GET and live in `useManageSources` (`settings`, null until loaded); the form is keyed on load so its drafts start from them and it stays disabled until then. Save PATCHes only `description` (never `exclude`, so stored exclude words stay as they are) and then shows the server-normalized values; errors inline under Save, success toast "Saved"; focus returns to Save.
- The "Describe what you're looking for…" hint follows the *saved* description, so it does not hide while the user types an unsaved draft.
- Description: `maxLength` 500 stops typing and the setter also cuts pasted text.
- Each source shows "Scanning…" or "Last checked <formatTimeAgo>" (nothing when never checked).
- Polling: after the initial load, ONE setTimeout chain in `useManageSources` re-fetches GET /vacancy-sources (requests never overlap): every 5 s while any source is scanning, else every 60 s (`getPollInterval`). The 60 s refresh only runs while `document.visibilityState === "visible"`; when hidden the chain stops and a `visibilitychange` back to visible resumes it (immediately if a full interval has passed). Cleared on unmount. Polls only update status fields of sources already in the local list (`mergePolledSources`), so a poll can't undo a concurrent add/remove or touch the settings draft. When a source goes scanning → not scanning, `SourcesPanel`'s `onScanFinished` runs and `notifyVacanciesChanged()` (from `entities/vacancy`) fires.
- `onSourcesChange(sources, removedSources)` feeds the Inbox source filter (no second GET). `removed_sources` comes from the load and polls; after a removal it is re-fetched in the background (latest response wins).
- Status notices (`SourcesNotices`, above the list): `status` from the same GET/polls; "Daily limit reached — N posts are waiting" ("1 post is waiting") and the AI-outage text, both may show. The `role="status"` region is always mounted so notices added by a poll are announced politely.
- Unavailable source: tinted row + "Unavailable — <last_error>" (fallback "Could not reach the source"); Remove stays enabled. The backend decides the 24 h threshold.
