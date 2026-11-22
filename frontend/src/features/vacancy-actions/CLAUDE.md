# Vacancy Actions Feature

Inbox card actions: "Open source" and "Dismiss" with a 5 s Undo (functional spec 2.3). `VacancyActions` goes into `VacancyCard`'s `actions` slot; the page owns the list and passes `onUpdate` / `onRemove` / `onRestore` to `useVacancyActions`.

- Mount `useVacancyActions` once per list, not per card: a dismissed card unmounts but its Undo must live on. Unmounting the hook (leaving the Inbox) closes open Undo toasts; the dismiss stays.
- "Open source" opens only http(s) URLs (`lib/helpers.ts`; URLs come from scraped posts) via `window.open(url, "_blank", "noopener,noreferrer")`, synchronously in the click so popup blockers allow it. Only a `new` card sends `POST /seen`; a failure flips the card back to new, no toast.
- Dismiss is optimistic. Undo waits for the dismiss request before calling restore (requests never cross) and re-inserts the card as `seen` after restore succeeds. A failed dismiss closes the Undo toast, puts the card back and shows an error toast.
- Every server change calls `notifyVacanciesChanged()` (nav badge).
