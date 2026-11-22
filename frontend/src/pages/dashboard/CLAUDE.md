# Dashboard Page

Route `/dashboard`: Board (kanban) / Timeline views plus the shared `ApplicationPanel` drawer.

- Deep link `?application=<id>` (target of the Inbox "Open application" toast and the "Open it" duplicate action) opens that application's panel, then removes the param with `replace`, so a reload or closing the panel does not reopen it. A new link while already on the dashboard opens again (the effect keys on the param value); an empty `?application=` is just removed. The param name and URL builder live in `@/shared/config` (`ROUTES`), shared with `features/vacancy-actions`. An unknown id shows "Application not found" in the panel.
