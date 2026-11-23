# Backlog: Jobbi

Small app improvements found during live testing. Not tied to a spec slice; pick up when planning the next spec or a polish pass.

Priority: High / Medium / Minor.

| # | Area | Item | Priority | Found |
|---|---|---|---|---|
| 7 | Bug: Add & tailor CV | After "adapt my CV" the AI answers as if it works from another application's CV. Cause found: the dialog's base CV defaults to the most recently updated CV, which is usually the previous tailored copy, so copies chain ("Base CV — Codery … — Welldin …") and carry the other company's content into the new chat. Fix: default to the user's base CV (see #8), never to a tailored copy; tailored copies are not offered as a base by default. | High | 2026-11-23, spec 009 live test |
| 8 | CV | Base CV: the user uploads (PDF/DOCX) or marks one CV as the base; every "Add & tailor CV" copies the base, and tailored copies are kept apart from it (label or separate list). | High | 2026-11-23, spec 009 live test |
| 4 | Inbox sources | Batch add: paste many sources at once (Telegram channels and Greenhouse/Lever links, one per line or comma-separated); each is validated as today, and the result reports what was added and what failed with the reason. `t.me/addlist/...` folder links cannot be expanded without a user Telegram session, so they get a clear message instead. | High | 2026-11-23, spec 009 live test |
| 5 | Vacancy discovery | Digest posts: one Telegram post can list several vacancies or only link to an external list (e.g. "8 vacancies from OZON" + link). Today the whole post is evaluated as one vacancy, so the card has no role or stack. Split a post into separate vacancies when it lists them; for link-only digests, decide whether to fetch the linked page or show the card as a digest. | Medium | 2026-11-23, spec 009 live test (@moskovskayarabota) |
| 6 | AI limits (app-wide) | When Groq rate limits are hit (requests/day, tokens/minute, tokens/day), the web app says so plainly: which limit, what is affected (Inbox evaluation, AI chat), when it resets (from the `x-ratelimit-reset-*` / `retry-after` headers). Today the chat shows a generic "Rate limit reached" and the Inbox only has notices for Jobbi's own daily cap and a long AI outage; a provider limit is not named. Optionally show remaining quota in Settings. | Medium | 2026-11-23, spec 009 live test |
| 1 | Forms (all) | The Save button is active only when the form has real changes (compare with the saved values; disabled again after reverting an edit). | Medium | 2026-11-23, spec 009 live test |
| 9 | Inbox page | The Inbox list and the Sources panel can be collapsed (each section has a show/hide toggle; the choice is remembered per browser), since both can take a lot of space. | Minor | 2026-11-23, spec 009 live test |
| 10 | Inbox sources | Remove on a source gets Undo (toast with a few seconds to restore, like Dismiss on cards); today removal is immediate and the source has to be added again, which repeats its initial scan check. | Minor | 2026-11-23, spec 009 live test |
| 2 | AI chat | Streaming shows raw Markdown first and then turns it into formatted text. Render the stream as formatted text from the start. | Minor | 2026-11-23, spec 009 live test |
| 3 | CV / AI chat | Check how a CV tailored through the AI chat is saved: the exported PDF contains only the heading. Consider replacing the form-based CV editor with free-text editing. | Minor | 2026-11-23, spec 009 live test |
