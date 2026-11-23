# CV Make Base Feature

"Make base" action for one CV on the CVs page (spec 011 §2.4): `POST /api/v1/cvs/{id}/make-base` → toast "Base CV updated" → `onMadeBase(updatedCv)`, where the page refetches its list (the previous base and, for a tailored copy, its section both change server-side, so a refetch is simpler than patching the list).

- Render it only for CVs that are not the base. A tailored copy made base comes back as `kind: "own"` for good.
- Accessible name is "Make base: <CV name>" (visible label first, WCAG 2.5.3) so each row's button is distinct. A ref drops double clicks; errors go through `handleApiError`.
