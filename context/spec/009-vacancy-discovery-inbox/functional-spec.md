# Functional Specification: Vacancy Discovery (Inbox)

- **Roadmap Item:** Job Alerts via Telegram (Phase 4 — Job Search Integrations): receive notifications about new matching jobs.
- **Status:** Draft
- **Author:** Poe (AI Product Analyst)

---

## 1. Overview and Rationale (The "Why")

The user finds vacancies in two places: public Telegram job channels and company career pages. Today they scroll channels and check career pages by hand, then retype what they find into Jobbi. Relevant posts get lost in the noise, and good roles are noticed late.

**Desired outcome:** Jobbi watches the user's chosen channels and companies, uses AI to pick out posts that are vacancies matching what the user described in their own words (any language, synonyms included), rates how well each fits the user's profile, and collects them in a new **Inbox**. The user reviews the Inbox and sends good ones to the tracker in one click, optionally going straight to tailoring a CV for it. New matches are announced through the Jobbi Telegram bot.

The Inbox is separate from the Application Tracker: a found vacancy is not an application until the user decides so. This keeps tracker metrics (response rate, pipeline) about real applications only.

**Success criteria:**
- The user no longer checks their job channels and target companies' career pages by hand.
- Under normal conditions (AI available, daily limit not reached), a matching vacancy appears in the Inbox at most 2 hours after it was posted.
- Moving a vacancy to the tracker takes one click and needs no retyping.

**Terms used below:**
- **Profile** — the desired role, location, remote preference and salary the user set in Settings. Empty fields are simply not taken into account.
- **Telegram linked** — the user connected the Jobbi bot in Settings (spec 006).
- **Daily summary** — the bot message each linked user receives once a day at their chosen time (spec 006).

---

## 2. Functional Requirements (The "What")

### 2.1 Managing sources and the search description

- **As a** user, **I want to** choose which channels and companies Jobbi watches and describe what I'm looking for, **so that** only relevant vacancies reach me.
  - **Acceptance Criteria:**
    - [ ] The Inbox page has a "Sources" panel listing watched Telegram channels, watched companies, the search description and exclude words.
    - [ ] The user can add a public Telegram channel by `@name` or `t.me/<name>` link. If the channel does not exist or is not public, the error "This channel is not public or does not exist" is shown within a few seconds and nothing is saved.
    - [ ] The user can add a company by its Greenhouse or Lever job-board link. A link that is not a Greenhouse/Lever board shows "Not a Greenhouse or Lever job board link"; a board that cannot be read shows "Could not read this job board". In both cases nothing is saved. Once added, the company name as published on the board is shown in the list.
    - [ ] Adding a channel or company that is already in the list shows "Already in your sources" and nothing changes. A user can watch at most 30 sources; adding a 31st shows "You can watch up to 30 sources".
    - [ ] The user can remove any channel or company. Vacancies already in the Inbox from it stay; in the source filter they appear under the old name marked "(removed)".
    - [ ] The user can write a **search description** in plain text, up to 500 characters (e.g. "Senior frontend, React or Vue, remote or EU, from 4000 €, no outsourcing"). Typing stops at 500 characters and a counter shows how many are used. It can be edited at any time; a change applies to posts found from then on.
    - [ ] The user can add and remove up to 50 **exclude words** (optional). A post or job whose title or text contains any of them as a whole word (so "java" does not exclude "javascript") is skipped and never shown. Letter case is ignored. A change applies to posts found from then on.
    - [ ] When a new source is added, Jobbi looks at its vacancies from the last 7 days. While this first scan runs, the source shows "Scanning…"; its results then appear in the Inbox. If the user re-adds a source they removed earlier, posts they already saw from it are not shown again.
    - [ ] Sources, the search description and exclude words are per user; one user never sees another user's sources or Inbox.

### 2.2 Finding and rating vacancies

- **As a** user, **I want** Jobbi to check my sources regularly and rate what it finds, **so that** I see the best-fitting vacancies first.
  - **Acceptance Criteria:**
    - [ ] Each source is checked every hour. The Sources panel shows, for each source, when it was last checked.
    - [ ] Every post or career-page job that Jobbi has not seen before, and that contains none of the exclude words, is evaluated by AI against the search description and the user's profile. The AI decides whether it is a vacancy and whether it matches the description.
    - [ ] Only posts the AI judges as matching vacancies appear in the Inbox. Non-vacancy posts (news, ads, memes) and non-matching vacancies are skipped and never shown.
    - [ ] Each match gets a fit rating **High**, **Medium** or **Low** with a one-sentence reason (e.g. "Remote React role, salary not stated"), plus the company name and role title when they can be determined (career-page jobs already carry both).
    - [ ] Reference cases for testing, with the description "Senior frontend, React, remote, from 4000 €" and an empty profile:
      - a post "Senior React Developer, fully remote, €5000–6000" → shown, High;
      - a post "Frontend developer (Vue), office in Berlin, salary not stated" → shown, Medium or Low;
      - a post "Our channel turns 5 years old today!" → not shown;
      - a post "Senior Java backend engineer, remote" → not shown.
    - [ ] If the user has no search description, the Sources panel shows "Describe what you're looking for to start finding vacancies." Posts found meanwhile are kept for up to 7 days and evaluated as soon as a description is saved.
    - [ ] If the AI cannot be reached, nothing is lost: posts wait and are evaluated at a later check. While the AI has been failing for more than 1 hour, the Sources panel shows a notice "Vacancy search is temporarily unavailable — new posts will be checked when it's back".
    - [ ] If a source cannot be read for 24 hours (for example, the channel became private or the board was removed), it is marked "Unavailable" in the Sources panel with the reason. The user can remove it. It becomes normal again as soon as a check succeeds.
    - [ ] Jobbi evaluates at most 300 posts per user per day (days counted in the user's timezone). When the limit is reached, the Sources panel shows "Daily limit reached — N posts will be checked tomorrow"; the waiting posts are evaluated the next day, oldest first.
    - [ ] A post or job Jobbi has seen before never creates a second card, including after it was dismissed or its card was deleted. If several posts point to the same job link (for example, the same vacancy reposted in two channels with a link to the company's job page), they appear as one card listing all the channels. Reposts without a shared job link may appear as separate cards.

### 2.3 The Inbox

- **As a** user, **I want** one list of found vacancies, **so that** I can review them and decide quickly.
  - **Acceptance Criteria:**
    - [ ] "Inbox" is a new item in the main navigation, with a badge showing the number of **new** vacancies. The badge updates right after the user acts on a card.
    - [ ] Each card shows: role title, company (or "Unknown company"), source(s), date posted (the post's date in Telegram, or the job's publication date on the career page), fit (High/Medium/Low) with its reason, and the first 300 characters of the text with "Show more" to expand the rest.
    - [ ] A card is **new** until the user clicks "Open source", "Add to tracker" or "Dismiss" on it; then it is **seen**. Reading or expanding a card does not change this.
    - [ ] "Open source" opens the original Telegram post or career-page job in a new tab.
    - [ ] "Add to tracker" opens a dialog with company, role (both required) and notes prefilled from the vacancy (notes = the full text). Confirming creates an application with status Researching and the job link. The card then leaves the Inbox and a confirmation with a link to the new application is shown.
    - [ ] If the tracker already has an application with the same job link, the dialog says "You already track this: <Company> — <Role>" and offers "Open it" and "Add anyway".
    - [ ] The dialog also offers **"Add & tailor CV"**: the user picks a base CV (default: the most recently updated one). Jobbi creates the application, makes a copy of the base CV named "<CV name> — <Company> <Role>" (shortened if too long), links the copy to the application, removes the card from the Inbox and opens the AI chat for that application with the first message pre-filled: "Adapt my CV to this vacancy". The message is sent only when the user presses Send. If the user has no CVs, the button is disabled with the hint "Create a CV first".
    - [ ] If creating the application or the CV copy fails, nothing is created, the card stays in the Inbox and the dialog shows "Could not add this vacancy. Please try again."
    - [ ] "Dismiss" removes the card at once and shows "Dismissed · Undo" for 5 seconds; Undo brings the card back. After that it never comes back.
    - [ ] The user can filter by source and by new/seen (filters combine), and sort by date posted (default: newest first) or by fit (High, then Medium, then Low; newest first within the same fit).
    - [ ] Empty Inbox shows: "No vacancies yet. Add channels or companies and describe what you're looking for in Sources."
    - [ ] Cards that were not added to the tracker are deleted 30 days after they were found. Jobbi still remembers them, so they never reappear. Vacancies added to the tracker live on as applications.

### 2.4 Alerts via Telegram

- **As a** user with Telegram linked, **I want** to hear about new matches, **so that** I can react quickly without opening Jobbi.
  - **Acceptance Criteria:**
    - [ ] After each hourly check that produced new matches for a user (including posts that waited for the AI or the daily limit), the Jobbi bot sends one message: "🔎 N new vacancies", then up to 10 lines "<Fit> · <Role> — <Company>" ordered by fit then newest, then "+M more in Inbox" if there are more, and a link to the Inbox.
    - [ ] No message is sent when a check finds nothing new.
    - [ ] Matches from the first 7-day scan of a newly added source are never announced by the bot (to avoid a burst); they only appear in the Inbox.
    - [ ] The daily summary includes a line "📥 N new vacancies in Inbox" when N > 0, where N is the same number as the Inbox badge.
    - [ ] Users without Telegram linked get no messages; the Inbox works the same.

---

## 3. Scope and Boundaries

### In-Scope

- Inbox page with Sources panel (channels, companies, search description, exclude words).
- Public Telegram channels (no Telegram login needed).
- Company career pages hosted on Greenhouse and Lever.
- Hourly checks; first 7-day scan for new sources; 30-day card lifetime with permanent memory of seen vacancies.
- AI search: every new post evaluated against a plain-text search description (match yes/no, High/Medium/Low fit + reason, company/role); optional exclude words.
- Inbox actions: Add to tracker (Researching), Add & tailor CV (application + CV copy + AI chat with a pre-filled message), Dismiss with Undo, Open source, filter and sort.
- Grouped bot alert per check and a line in the daily summary.

### Out-of-Scope

- **HeadHunter Integration** and **LinkedIn Integration** (separate roadmap items).
- Private Telegram channels and groups, or reading Telegram as the user's own account.
- Career pages not on Greenhouse/Lever — possible later spec.
- Managing sources, the search description or the Inbox from the Telegram bot (bot only notifies).
- Alerts filtered by fit threshold; per-source search descriptions; changing the daily limit from the UI.
- Re-evaluating past posts when the search description or exclude words change (applies to new posts only).
- Merging reposts that share no job link.
- Editing vacancy text in the Inbox; bulk actions.
- Auto-applying to vacancies.
