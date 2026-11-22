# Manage Sources Feature

Inbox "Sources" panel (`SourcesPanel`): add a Telegram channel by `@name` / `t.me/name`, list watched sources with "Scanning…" / "Unavailable" + reason, remove a source (no confirm), and the "What are you looking for?" form (search description + exclude words).

- State lives in `model/use-manage-sources.ts`. Add errors are shown inline under the input (`getErrorMessage` — the backend's 400/409 `detail` text is user-facing); remove errors go to a toast.
- The add form stays disabled until the initial list loads, so a late GET can't overwrite a just-added source.
- Focus: after Add (success or error) it returns to the input; after Remove it moves to the next Remove button, else the previous one, else the input (`lib/helpers.ts`).
- The backend checks a channel live (up to ~10 s), so the input is read-only and "Add" shows loading while a request runs; a ref blocks double submits.
- Search settings: `SearchSettingsForm` + `model/use-search-settings-form.ts`. Saved settings come from the same GET and live in `useManageSources` (`settings`, null until loaded); the form is keyed on load so its drafts start from them and it stays disabled until then. Save PATCHes both fields and then shows the server-normalized values; errors inline under Save, success toast "Saved"; focus returns to Save.
- The "Describe what you're looking for…" hint follows the *saved* description, so it does not hide while the user types an unsaved draft.
- Description: `maxLength` 500 stops typing and the setter also cuts pasted text. Exclude words use `ChipInput` from `@/shared/ui` (50 max, 64 chars each).
- Each source shows "Scanning…" or "Last checked <formatTimeAgo>" (nothing when never checked).
- Polling: while any source is scanning, `useManageSources` re-fetches GET /vacancy-sources every 5 s (setTimeout chain, so requests never overlap; cleared on unmount or when nothing scans). Polls only update status fields of sources already in the local list (`mergePolledSources`), so a poll can't undo a concurrent add/remove or touch the settings drafts. When a source goes scanning → not scanning, `SourcesPanel`'s `onScanFinished` runs and `notifyVacanciesChanged()` (from `entities/vacancy`) fires.
- `onSourcesChange(sources, removedSources)` feeds the Inbox source filter (no second GET). `removed_sources` comes from the load and polls; after a removal it is re-fetched in the background (latest response wins).
- Not here yet (later slices): status notices (AI unavailable, daily limit).
