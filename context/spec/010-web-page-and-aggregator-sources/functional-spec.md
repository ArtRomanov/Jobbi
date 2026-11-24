# Functional Specification: Web Page and Aggregator Sources

- **Roadmap Item:** Phase 4 — Job Search Integrations: extends Vacancy Discovery (spec 009) with job aggregators and company career pages.
- **Status:** Draft
- **Author:** Poe (AI Product Analyst)

---

## 1. Overview and Rationale (The "Why")

Spec 009 watches Telegram channels and Greenhouse/Lever boards. Most vacancies the user cares about are on **job aggregators** (hirify.me, geekjob.ru, hirehi.ru, careerspace.app, ingamejob.com) and on **company career pages** that use none of those boards (Playrix, Ostrovok, Wrike, EPAM, Avito…). The user checks these by hand today.

**Desired outcome:** the user pastes any aggregator search link or career-page link into Sources, with the site's own filters already in the link (e.g. `?q=react&remote=1`). Jobbi checks it every hour, opens every new vacancy to read its text, and runs it through the same pipeline as spec 009 (exclude words → AI match and fit → Inbox → bot alert). No per-site setup in code: everything is configured in the UI.

**Success criteria:**
- The user can watch an aggregator search or career page by pasting its link, with no code change per site.
- A matching vacancy appears in the Inbox at most 2 hours after it appears on the page (AI available, daily limit not reached).
- Changing a source (for example a search's filters) takes one Edit, with no lost history.

**Terms used below:**
- **Web page source** — a watched link that is not Telegram and not a known job board (Greenhouse, Lever, Teamtailor).
- **Listing** — the page the link opens: a list of vacancies, possibly split into numbered pages.
- **Job link** — the link to one vacancy found on the listing.
- All other terms (profile, daily limit, Unavailable, first scan, bot alerts) are as in spec 009.

---

## 2. Functional Requirements (The "What")

### 2.1 Adding a Web page source

- **As a** user, **I want to** paste an aggregator search or career-page link, **so that** Jobbi watches it for me.
  - **Acceptance Criteria:**
    - [ ] Besides Telegram `@name` and t.me links (spec 009), the Sources panel input accepts any `http(s)` link. A Greenhouse, Lever or Teamtailor link is added as that board (spec 009; Teamtailor in 2.3); any other link becomes a Web page source.
    - [ ] The preview (below) has an optional field **"Job link contains"** (1–100 characters, e.g. `/vacancy/`); the first preview runs without it. When set, only links whose address contains this text count as vacancies; when empty, Jobbi picks job links by itself.
    - [ ] On "Add", Jobbi opens the link within 15 seconds and shows a **preview**: "Found N vacancies" (N counts vacancies on the first page of the listing) and the first 5 vacancy titles in the order the site shows them, with "Save" and "Cancel". The user can change "Job link contains" in the preview and re-check. Nothing is saved until "Save". If the page does not respond within 15 seconds, "Could not open this page" is shown.
    - [ ] If the page links to a Greenhouse, Lever or Teamtailor job board, the preview also shows "This page uses <Greenhouse|Lever|Teamtailor> — add the board instead for full job texts and dates" with a button "Add the board". The button adds that board exactly like pasting its link (spec 009 / 2.3) and closes the preview. The user can still save the page itself.
    - [ ] The add form shows the hint "Sort the page by newest first before copying the link", because Jobbi looks for new vacancies at the top of the listing (see 2.4).
    - [ ] If the page cannot be opened: "Could not open this page". If it opens but no vacancies are found (including pages that build their content with JavaScript): "No vacancies found on this page. Check the link or set 'Job link contains'." In both cases nothing is saved.
    - [ ] Links to local or private network addresses (e.g. `localhost`, `192.168.x.x`) and links that are not http(s) show "This link can't be used" and are never opened.
    - [ ] **Name:** defaults to the site's domain (e.g. "geekjob.ru"). The user can set their own name, up to 100 characters (e.g. "Geekjob — React remote"), when adding or later via Edit.
    - [ ] The same link already in the list shows "Already in your sources". Letter case of the domain, a trailing slash and tracking parameters (`utm_*`) are ignored. The same site with different filters is a different source. Web page sources count toward the 30-source limit.
    - [ ] **First scan:** every vacancy listed at the moment of saving is remembered as already seen and is never shown; only vacancies that appear later reach the Inbox. Right after saving, the source shows "Watching since <time>" instead of "Scanning…".

### 2.2 Editing a source

- **As a** user, **I want to** change any source, **so that** I don't have to remove and re-add it.
  - **Acceptance Criteria:**
    - [ ] Every source (Telegram, Greenhouse, Lever, Teamtailor, Web page) has "Edit" to change its link and its name (up to 100 characters). Web page sources also have "Job link contains".
    - [ ] Changing only the name takes effect at once; Inbox cards and the source filter show the new name. An empty name falls back to the default (the domain for Web pages, the channel or board name otherwise).
    - [ ] **Web page:** a changed link or "Job link contains" shows the same preview as adding, with the same errors as in 2.1. After "Save", vacancies listed at that moment are remembered as seen; vacancies seen before are never shown again. Cards already in the Inbox stay, under the source's current name.
    - [ ] **Telegram / Greenhouse / Lever / Teamtailor:** a changed link is checked like a new one (same errors and "Already in your sources" as when adding). It works like "remove the old one and add the new one" in one step: cards from the old channel or board stay and appear in the source filter under the old name marked "(removed)", and the new one gets the normal 7-day first scan. The link may switch to any kind (e.g. a Lever board replaced with a Web page link).
    - [ ] Edit is not available while a first-scan attempt is running; it becomes available as soon as that attempt completes or fails (so a mistyped link can be fixed without waiting 24 hours).

### 2.3 Teamtailor boards

- **As a** user, **I want to** watch companies that publish jobs on Teamtailor, **so that** I get their full job texts like Greenhouse/Lever.
  - **Acceptance Criteria:**
    - [ ] The user can add a company by its `<company>.teamtailor.com` link. It behaves like Greenhouse/Lever in spec 009: name taken from the board, 7-day first scan, full job text.
    - [ ] Errors: a link that is not a known board shows "Not a Greenhouse, Lever or Teamtailor job board link" only when it mentions one of these services; a board that cannot be read shows "Could not read this job board". Nothing is saved.

### 2.4 Checking a Web page source

- **As a** user, **I want** Jobbi to pick up every new vacancy on my pages, **so that** I don't miss any.
  - **Acceptance Criteria:**
    - [ ] Each Web page source is checked every hour. Jobbi reads the listing page by page, up to **5 pages**, and stops at the first page that contains a vacancy it has already seen.
    - [ ] Per check, Jobbi opens at most **30 new vacancies** per source to read their text; the rest are taken at the next check and nothing is lost.
    - [ ] Each opened vacancy goes through spec 009 unchanged: exclude words, AI match and fit, the daily limit of 150 evaluations, merging by job link, 30-day card lifetime. Company and role come from the AI (as for Telegram posts); the listing title is used as the role when the AI can't determine one.
    - [ ] If a vacancy's own page cannot be opened, it is retried at the next check; after 3 failed checks it is evaluated using only its title from the listing.
    - [ ] The card's "date posted" is the date on the vacancy's page when Jobbi can find one, otherwise the time Jobbi found it.
    - [ ] **Unavailable** (after 24 hours, as in spec 009) has two reasons for Web page sources: "Could not reach the source" (the page does not open) and "No vacancies found — check the link or the 'Job link contains' field" (the page opens but lists no vacancies). The mark clears on the next successful check.
    - [ ] Bot alerts and the daily summary line work as in spec 009, unchanged.

### 2.5 Reference cases for testing

- [ ] `https://career.ostrovok.ru/vacancy` with "Job link contains" `/vacancy/` → the preview lists vacancy titles, not menu items.
- [ ] The same link without the field → the preview still finds vacancies; menu items like "About us" may appear and are acceptable.
- [ ] A geekjob.ru search link with a filter → after saving nothing appears; when a new matching vacancy is published, it appears in the Inbox within 2 hours.
- [ ] Editing that source from `q=react` to `q=vue` → the preview shows Vue vacancies; after saving, React cards stay and only new Vue vacancies arrive.
- [ ] Editing a Telegram source to another channel → old cards show "<old name> (removed)" in the source filter; the new channel shows "Scanning…" and its last 7 days are evaluated.
- [ ] `http://localhost:8000/` or `http://192.168.1.1/` → "This link can't be used"; nothing is opened or saved.

### 2.6 Follow-up: Ashby boards, geekjob search links, blocked sites

- **As a** user, **I want to** watch companies on Ashby, see real results for geekjob.ru search links and understand why a site can't be read, **so that** fewer of my sources end up empty or "Could not open this page".
- **Acceptance Criteria:**
    - [ ] **Ashby boards.** The user can add a company by its `jobs.ashbyhq.com/<company>` link (with or without `https://`, also a single job's link `jobs.ashbyhq.com/<company>/<job id>`). It behaves like Greenhouse/Lever: kind label "Ashby", name = the company slug with capital letters (Ashby does not publish the company name), full job texts and publish dates, first scan = jobs published in the last 7 days.
    - [ ] `jobs.ashbyhq.com/manychat` → added as "Manychat"; its jobs (21 at the time of writing) appear as the board's vacancies after the first scan.
    - [ ] An unknown company on Ashby → "Could not read this job board". A link on an Ashby host that is not a board (e.g. `www.ashbyhq.com/...`, `jobs.ashbyhq.com/` without a company) → "Not a Greenhouse, Lever, Teamtailor or Ashby job board link" (this text replaces the earlier one for all boards). Look-alikes such as `jobs.ashbyhq.com.evil.com/manychat` are treated as ordinary web pages.
    - [ ] A career page that links to or embeds an Ashby board shows "This page uses Ashby — add the board instead" in the preview, like the other boards.
    - [ ] **geekjob.ru search links.** A geekjob.ru search link with at least one filter (e.g. `geekjob.ru/vacancies?qs=react`) is read from the site's own search results, newest first: the preview of `geekjob.ru/vacancies?qs=react` shows "Found N vacancies" and React job titles instead of "No vacancies found". Saving, hourly checks, opening job pages, exclude words and AI work as for any other web page. `geekjob.ru/vacancies` without filters works as before.
    - [ ] **Blocked sites.** A site that answers with a bot-protection challenge (e.g. Cloudflare "Just a moment…") → preview, Add and Edit show "This site blocks automated readers"; nothing is saved. The same text is shown when a job board's API answers with such a challenge. `careers.manychat.com/positions` → this text.
    - [ ] A saved web page that starts answering with such a challenge → after 24 hours of failed checks the row shows "Unavailable — This site blocks automated readers". A job page behind such a challenge is not retried again in the same check.
    - [ ] Every spelling of one geekjob.ru search (`www.`, `/vacancies/2`, parameters the site ignores such as `or`, `money`, `f`, a repeated `qs`) is the same source: adding it a second time shows "Already in your sources", and editing a source to another spelling of the same search changes nothing.
    - [ ] A geekjob.ru results page that lists only archived vacancies does not end the listing: the next pages are still read (up to 5).
    - **Known limitation:** geekjob.ru's "by date" order is by last edit, not by first publication. An old vacancy that was beyond the pages read when the source was saved, and that the employer later edits, moves to the top and arrives in the Inbox as new. This cannot be avoided from our side (the search results carry no creation date).

---

## 3. Scope and Boundaries

### In-Scope

- Web page source: add with preview, optional "Job link contains", custom name, first scan = "only new".
- Edit for every source kind (name, link; "Job link contains" for Web pages).
- Hourly checks with pagination (up to 5 pages, stop at a seen vacancy) and up to 30 opened vacancies per check per source.
- Teamtailor boards on `<company>.teamtailor.com`.
- New error and Unavailable messages listed above.

### Out-of-Scope

- **HeadHunter Integration** and **LinkedIn Integration** (separate roadmap items).
- Pages that build their vacancy list with JavaScript (they get the "No vacancies found" error).
- Finding new vacancies on listings that are not sorted newest first (a new vacancy below already-seen ones may be missed; the add form hints to sort by newest).
- Sites that need a login, a captcha or a paid API (e.g. hirehi.ru PRO API).
- Teamtailor on a company's own domain; other ATSs (Workable, Ashby, SmartRecruiters…) — possible later.
- Changing per-check limits or the daily AI limit from the UI; per-source search descriptions.
- Showing vacancies that were already listed when a Web page source was added or edited.
