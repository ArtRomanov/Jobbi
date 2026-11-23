# Inbox Filters Feature

Controlled filter bar for the Inbox (`InboxFilters`): Source select, New/Seen/All and Newest/Best fit (`SegmentedControl` from `@/shared/ui`). The page owns the value (`DEFAULT_INBOX_FILTERS`) and the source lists; this slice fetches nothing.

- Source option values are source **keys** (the API filters by key); labels are display names. Removed sources that old cards still carry come from `removed_sources` and get " (removed)"; forwarded-post channels (key prefix `tg_forward:`) get " (forwarded)". A selected key missing from both lists keeps an option so the select never lies.
- `hasActiveFilters` ignores sort; the page uses it to pick the "no matches" vs "no vacancies yet" empty state.
