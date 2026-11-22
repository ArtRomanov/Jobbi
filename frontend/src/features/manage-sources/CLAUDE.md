# Manage Sources Feature

Inbox "Sources" panel (`SourcesPanel`): add a Telegram channel by `@name` / `t.me/name`, list watched sources with "Scanning…" / "Unavailable" + reason, remove a source (no confirm).

- State lives in `model/use-manage-sources.ts`. Add errors are shown inline under the input (`getErrorMessage` — the backend's 400/409 `detail` text is user-facing); remove errors go to a toast.
- The add form stays disabled until the initial list loads, so a late GET can't overwrite a just-added source.
- Focus: after Add (success or error) it returns to the input; after Remove it moves to the next Remove button, else the previous one, else the input (`lib/helpers.ts`).
- The backend checks a channel live (up to ~10 s), so the input is read-only and "Add" shows loading while a request runs; a ref blocks double submits.
- Not here yet (later slices): search description, exclude words, last-checked time, status notices, polling while scanning.
