# CV Text Editor Feature

The CV editor (functional spec 011 §2.1): name field + one textarea for the whole CV, formatting hint, live preview (`CvTextPreview` from `@/entities/cv`, via `useDeferredValue`). Wide screens: editor and preview side by side; phone width (`PHONE_MEDIA_QUERY`): `SegmentedControl` tabs "Edit" / "Preview", "Edit" first. `pages/cv-editor` owns loading, saving, the toast and the `version` sent with PATCH.

- `initialValues` are read once (on mount); the page must not remount the editor after a save, or the user's draft is reset.
- Text limit 20 000 (UTF-16 units, the same unit `maxLength` counts). Typing stops via `maxLength`; paste is intercepted and cut to fit by `insertTextWithinLimit` (never splits a surrogate pair), caret placed after the pasted part.
- Name: `maxLength` 255, trimmed before save; blank → "Required" and `onSave` is not called.
- The draft lives in `model/use-cv-text-draft.ts` so dirty tracking, the counter and the unsaved-changes guard (Slice 3) can hook in there.
