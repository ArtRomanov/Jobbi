# Functional Specification: Vacancy Discovery (Inbox)

- **Roadmap Item:** Telegram Bot Integration → Job Alerts via Telegram (Phase 4 — Job Search Integrations V1.1)
- **Status:** Draft
- **Author:** Poe (AI Product Analyst)

---

## 1. Overview and Rationale (The "Why")

The user finds vacancies in two places: public Telegram job channels and company career pages. Today they scroll channels and check career pages by hand, then retype what they find into Jobbi. Relevant posts get lost in the noise, and good roles are noticed late.

**Desired outcome:** Jobbi watches the user's chosen channels and companies, uses AI to pick out posts that are vacancies matching what the user described in their own words (any language, synonyms included), rates how well each fits the user's profile, and collects them in a new **Inbox**. The user reviews the Inbox and sends good ones to the tracker in one click. New matches are announced through the Jobbi Telegram bot.

The Inbox is separate from the Application Tracker: a found vacancy is not an application until the user decides so. This keeps tracker metrics (response rate, pipeline) about real applications only.

**Success criteria:**
- The user no longer checks their job channels and target companies' career pages by hand.
- A matching vacancy appears in the Inbox within about an hour of being posted.
- Moving a vacancy to the tracker takes one click and needs no retyping.

---

## 2. Functional Requirements (The "What")

### 2.1 Managing sources and the search description

- **As a** user, **I want to** choose which channels and companies Jobbi watches and describe what I'm looking for, **so that** only relevant vacancies reach me.
  - **Acceptance Criteria:**
    - [ ] The Inbox page has a "Sources" panel listing watched Telegram channels, watched companies, the search description and exclude words.
    - [ ] The user can add a Telegram channel by `@name` or `t.me/<name>` link. If the channel does not exist or is not public, an error is shown immediately ("This channel is not public or does not exist") and nothing is saved.
    - [ ] The user can add a company by its Greenhouse or Lever job-board link. If the link is not a recognised Greenhouse/Lever board or the board cannot be read, an error is shown immediately and nothing is saved. The company name is shown in the list once added.
    - [ ] The user can remove any channel or company. Vacancies already in the Inbox from it stay.
    - [ ] The user can write a **search description** in plain text, up to 500 characters (e.g. "Senior frontend, React or Vue, remote or EU, from 4000 €, no outsourcing"). It can be edited at any time; a change applies to posts found from then on.
    - [ ] The user can add and remove **exclude words** (optional). A post containing any of them is skipped without being sent to AI. Matching ignores letter case.
    - [ ] When a new source is added, Jobbi scans its vacancies from the last 7 days; the results appear in the Inbox after that scan.
    - [ ] Sources, the search description and exclude words are per user; one user never sees another user's sources or Inbox.

### 2.2 Finding and scoring vacancies

- **As a** user, **I want** Jobbi to check my sources regularly and rate what it finds, **so that** I see the best-fitting vacancies first.
  - **Acceptance Criteria:**
    - [ ] Jobbi checks all sources of all users every hour.
    - [ ] Every **new** post or career-page job (not seen before) that contains none of the exclude words is evaluated by AI against the search description and the user's profile (desired role, location, remote preference, salary). The AI decides: is this a vacancy, and does it match the description?
    - [ ] Only posts the AI judges as matching vacancies appear in the Inbox. Non-vacancy posts (news, ads, memes) and non-matching vacancies are skipped.
    - [ ] Each match gets a fit rating **High**, **Medium** or **Low** with a one-sentence reason (e.g. "Remote React role, salary not stated"), plus the company name and role title when they can be determined (career-page jobs already carry both).
    - [ ] If the user has no search description, nothing is evaluated and the Sources panel shows a hint: "Describe what you're looking for to start finding vacancies."
    - [ ] If AI is unavailable, new posts wait and are evaluated on the next check; nothing is lost. If a source's posts cannot be evaluated for 24 hours, the Sources panel shows "Vacancy search is temporarily unavailable".
    - [ ] Jobbi evaluates at most a daily limit of posts per user (default 300); posts above the limit wait for the next day, oldest first.
    - [ ] The same vacancy is shown once: a post or job already seen (same link, or the same post in the same channel) does not create a second card, including after it was dismissed.

### 2.3 The Inbox

- **As a** user, **I want** one list of found vacancies, **so that** I can review them and decide quickly.
  - **Acceptance Criteria:**
    - [ ] "Inbox" is a new item in the main navigation, with a badge showing the number of new (not yet opened) vacancies.
    - [ ] Each card shows: role title, company (or "Unknown company"), source (channel name or company), date posted, fit (High/Medium/Low) with its reason, and the first lines of the text.
    - [ ] A card is "new" until the user opens or acts on it; then it becomes "seen".
    - [ ] "Open source" opens the original Telegram post or career-page job in a new tab.
    - [ ] "Add to tracker" creates an application with status Researching, filling company, role, job link, and the full post text as notes; missing company or role can be typed in before confirming. The card then leaves the Inbox and the user sees a confirmation with a link to the new application.
    - [ ] The "Add to tracker" dialog also offers **"Add & tailor CV"**: the user picks a base CV (default: the most recently updated one). Jobbi creates the application, makes a copy of the base CV named "<CV name> — <Company> <Role>", links the copy to the application, and opens the AI chat for that application with the first message pre-filled: "Adapt my CV to this vacancy". The message is sent only when the user presses Send. If the user has no CVs, the button is disabled with the hint "Create a CV first".
    - [ ] If any step of "Add & tailor CV" fails, nothing is created (no application, no CV copy) and the card stays in the Inbox with an error message.
    - [ ] "Dismiss" removes the card from the Inbox; it never comes back.
    - [ ] The user can filter by source and by new/seen, and sort by date posted (default: newest first) or by fit (High first).
    - [ ] Empty Inbox shows: "No vacancies yet. Add channels or companies and describe what you're looking for in Sources."
    - [ ] Vacancies that were dismissed or left untouched are deleted after 30 days. Vacancies added to the tracker live on as applications.

### 2.4 Alerts via Telegram

- **As a** user with Telegram linked, **I want** to hear about new matches, **so that** I can react quickly without opening Jobbi.
  - **Acceptance Criteria:**
    - [ ] When an hourly check finds new matches for a user, the Jobbi bot sends one message listing them (role, company, fit), with a link to the Inbox — not one message per vacancy. If there are more than 10, the message lists the top 10 by fit and says "+N more in Inbox".
    - [ ] No message is sent when a check finds nothing new.
    - [ ] The initial 7-day scan of a newly added source does not send a bot message (to avoid a burst); its results only appear in the Inbox.
    - [ ] The daily summary includes a line "📥 N new vacancies in Inbox" when N > 0.
    - [ ] Users without Telegram linked get no messages; the Inbox works the same.

---

## 3. Scope and Boundaries

### In-Scope

- Inbox page with Sources panel (channels, companies, search description, exclude words).
- Public Telegram channels via their public web preview.
- Company career pages hosted on Greenhouse and Lever.
- Hourly checks; initial 7-day scan for new sources; 30-day retention.
- AI search: every new post evaluated against a plain-text search description (match yes/no, High/Medium/Low fit + reason, company/role); optional exclude words as a pre-filter.
- Inbox actions: Add to tracker (Researching), Dismiss, Open source, filter and sort.
- Grouped bot alert per check and a line in the daily summary.

### Out-of-Scope

- **HeadHunter Integration** and **LinkedIn Integration** (separate roadmap items).
- Private Telegram channels and groups, or reading Telegram as the user's own account.
- Career pages not on Greenhouse/Lever (generic HTML parsing) — possible later spec.
- Managing sources, the search description or the Inbox from the Telegram bot (bot only notifies).
- Alerts filtered by fit threshold; per-source search descriptions.
- Re-evaluating past posts when the search description changes (applies to new posts only).
- Editing vacancy text in the Inbox; bulk actions.
- Auto-applying to vacancies.
