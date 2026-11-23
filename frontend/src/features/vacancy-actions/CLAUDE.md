# Vacancy Actions Feature

Inbox card actions: "Open source", "Add to tracker" (dialog) and "Dismiss" with a 5 s Undo (functional spec 2.3). `VacancyActions` goes into `VacancyCard`'s `actions` slot; the page owns the list and passes `onUpdate` / `onRemove` / `onRestore` to `useVacancyActions`, then wires its `markSeen` / `completeAdd` into `VacancyActions` (`onMarkSeen` / `onAdded`).

- Mount `useVacancyActions` once per list, not per card: a dismissed card unmounts but its Undo must live on. Unmounting the hook (leaving the Inbox) closes open Undo toasts; the dismiss stays.
- "Open source" opens only http(s) URLs (`isSafeExternalUrl` from `@/shared/lib`, shared with application-panel; URLs come from scraped posts) via `window.open(url, "_blank", "noopener,noreferrer")`, synchronously in the click so popup blockers allow it. Only a `new` card sends `POST /seen` (`markSeen`); a failure flips the card back to new, no toast.
- Dismiss is optimistic. Undo waits for the dismiss request before calling restore (requests never cross) and re-inserts the card as `seen` after restore succeeds. A failed dismiss closes the Undo toast, puts the card back and shows an error toast.
- Every server change calls `notifyVacanciesChanged()` (nav badge).

## Add to tracker
- Clicking "Add to tracker" marks a new card seen (spec 2.3), like "Open source".
- `AddToTrackerDialog` is mounted per card only while open (state in `VacancyActions`); it unmounts with the card on success. Schema in `model/schemas.ts` (company/role trimmed, "Required", ≤ 255).
- CV select ("CV to tailor", spec 011 §2.6): options from `buildCvSelectChoices` (`entities/cv`) — own CVs first (base first, labelled "(base)"), then a "Tailored copies" `<optgroup>` (`FormSelect` `groups`). The user's base CV (`is_base`) is preselected once the list arrives (unless the user already picked one). With no base nothing is preselected: an empty "Choose a CV" first option, "Add & tailor CV" disabled until a CV is chosen, and the hint "Choose a CV to tailor, or mark one as base on the CVs page." under the select (also the disabled button's description). There is no "most recently updated" fallback any more — that chained tailored copies (backlog #7).
- With no CVs at all "Add & tailor CV" is disabled with "Create a CV first" (other hints while loading / on load failure). Plain "Add to tracker" never needs a CV. Only tailor sends `base_cv_id` (the API field name; it is the chosen CV, base or not).
- Duplicate warning comes from the card's `existing_application` OR the structured 409 (`getDuplicateApplication`, a race). While the warning shows, the two add buttons send nothing (it would be a guaranteed 409): they remember the mode and focus "Add anyway". "Add anyway" sends the last pressed button's mode (plain if none) with `allow_duplicate: true`. The warning text is the dialog's `aria-describedby`. "Open it" = close + `markSeen` + `ROUTES.dashboardApplication(id)` (card stays).
- Success: badge notify → `onAdded` (list removes the card) → plain: toast with "Open application" link (8 s); tailor: navigate to `/applications/<id>/chat` with router state `ChatRouteState` `{draft: "Adapt my CV to this vacancy"}` (`entities/chat`), never sent automatically.
- 409 "Already added" (added in another tab): not an error — dialog closes, card leaves, info toast "Already in your tracker".
- Other failures: inline error — `getErrorMessage` for 404/409 (server text), else "Could not add this vacancy. Please try again.". A ref blocks double submits; Escape/backdrop are blocked while submitting.
- URLs come from `ROUTES` in `@/shared/config` (features cannot import pages).
- Card buttons carry per-card accessible names ("Dismiss <role> at <company>", "Open source for …", "Add to tracker: …") via `getVacancyLabel` from the entity; the visible label stays first (WCAG 2.5.3).
