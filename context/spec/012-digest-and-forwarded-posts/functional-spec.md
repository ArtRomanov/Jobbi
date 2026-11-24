# Functional Specification: Digest Posts and Forwarded Posts

- **Roadmap Item:** Vacancy Discovery (Inbox): follow-up to spec 009 (product backlog #5 "Digest posts") and Quick Add from Telegram for posts forwarded from channels.
- **Status:** Draft
- **Author:** Poe (AI Product Analyst)

---

## 1. Overview and Rationale (The "Why")

Many Telegram job channels publish **digests**: one post that lists several vacancies. Jobbi rates such a post as one vacancy. The user gets a single card with no clear role, a fit that is averaged over unrelated jobs, and the text of every listed job. For example, "100% remote jobs 18 Nov" from "Digital nomads. Work from anywhere" became one Low card for all its roles. The few relevant roles are lost among the irrelevant ones.

Jobbi can only read public channels. Since PR #35 the user can forward a post from any channel, private ones included, to the Jobbi bot, and it goes to the Inbox. No spec describes that flow yet. This spec does, and aligns its rules with posts from watched channels.

**Desired outcome:** each vacancy in a digest is judged on its own, and only matching ones become cards, each with its own role, company, fit, reason, text and job link. Forwarded posts follow the same rules, and the bot tells the user what came of them.

**Success criteria:**
- A digest listing N vacancies, K of which match, gives exactly K cards (K ≤ 20), each showing only its own vacancy.
- Under normal conditions (AI available, daily limit not reached), the bot reports the result of a forwarded post ("cards added" or "none match") within about 2 minutes.

**Terms used below:**
- **Digest:** a post that lists more than one open position.
- **Vacancy fragment:** the lines of a digest that describe one vacancy (its heading and the lines under it).
- **Link-only digest:** a post that announces vacancies without listing them, e.g. "8 vacancies from OZON" + a link.
- **Forwarded post:** a channel post the user forwarded to the Jobbi bot in a private chat.
- Other terms (profile, job link, Telegram linked, daily summary) are as in spec 009.

---

## 2. Functional Requirements (The "What")

### 2.1 Digest posts

- **As a** user, **I want** each vacancy in a digest to be judged on its own, **so that** I only see the roles I'm looking for.
  - **Acceptance Criteria:**
    - [ ] When a post from a watched Telegram channel lists several vacancies, each vacancy is rated against the search description and profile with the match and fit rules of spec 009 §2.2. Only matching vacancies become cards; the others are not shown.
    - [ ] Each card from a digest shows its own role and company (the digest's company when the post names one for all its vacancies; otherwise "Unknown company" when not stated), its own fit and reason, its vacancy fragment as the text, and the post's date as the date posted. "Open source" opens the whole post.
    - [ ] A digest card's job link is the first link inside its fragment that does not point to Telegram. A vacancy without such a link uses the post's own link (for "Add to tracker" and "Open source") and never merges with other cards.
    - [ ] "Add to tracker" pre-fills the notes with the card's text (its fragment).
    - [ ] At most 20 cards are created from one post; matching vacancies beyond the 20th are ignored.
    - [ ] A post with a single vacancy works exactly as before: one card whose text is the whole post.
    - [ ] A link-only digest works as before: it is rated as one post.
    - [ ] A digest counts as **one post** toward the daily limit of 150, however many vacancies it lists. The limit notice keeps saying "N posts are waiting".
    - [ ] A post Jobbi has seen never produces cards again. Dismissing, or adding to the tracker, one card from a digest does not affect the other cards from it.
    - [ ] A vacancy from a digest whose job link matches an existing card merges into that card (the card lists both sources), as reposts do in spec 009.
    - [ ] Alerts count cards: a digest with 3 matching vacancies adds 3 lines to the combined bot alert (spec 009 §2.4).
    - [ ] Reference cases, with the description "Senior frontend, React, remote, from 4000 €" and an empty profile:
      - a digest listing (1) "Senior React Developer, remote, €5000", (2) "Senior Java backend engineer, remote", (3) "Frontend developer (Vue), office in Berlin" and (4) "Product designer, remote" → 2 cards: (1) High and (3) Low;
      - a digest of 6 non-IT jobs (sales, support, logistics) → no cards;
      - "8 vacancies from OZON" + a link → rated as one post, as today.
    - [ ] Cards that existed before this change are not split again.
    - [ ] **Exclude words are switched off.** One excluded word could drop a whole digest with several relevant vacancies, so the exclude words block disappears from the Sources panel and no post or vacancy is skipped because of them. Words the user already saved are kept but ignored (removing them completely is backlog #12).
    - [ ] Jobbi reads up to 3,000 characters of each post. If any post read for the user in the last 24 hours was longer, the daily summary (spec 006) adds the line "✂️ N posts in the last 24 hours were longer than Jobbi reads (3,000 characters); vacancies at their end may have been missed."

### 2.2 Forwarding posts to the bot

- **As a** user with Telegram linked, **I want to** forward a post from any channel to the Jobbi bot, **so that** vacancies from private channels Jobbi cannot read reach my Inbox too.
  - **Acceptance Criteria:**
    - [ ] A post forwarded from a public or private channel to the bot's private chat is rated like a post from a watched channel: digests are split and only matching vacancies become cards.
    - [ ] The bot replies at once: "📥 Got it. Jobbi will rate it and add matching vacancies to your Inbox." Without a search description it replies "📥 Saved. Describe what you're looking for on the Sources page so Jobbi can rate it."; the post then waits up to 7 days, as in spec 009.
    - [ ] After the post is rated (usually within 2 minutes), the bot sends a second message as a reply to the forwarded post:
      - digest with matches: "✅ 2 of 6 vacancies match. Added to your Inbox.";
      - single vacancy that matches: "✅ Added to your Inbox: <Fit> · <Role> — <Company>" ("Unknown role" / "Unknown company" when missing);
      - single vacancy that matches a card already in the Inbox (same job link, merged into it): "<Role> — <Company> is already in your Inbox.";
      - in a digest, vacancies merged into existing cards count as matches in "N of M vacancies match";
      - a vacancy or digest with no match: "None of the vacancies in this post match your search.";
      - not a vacancy: "This post doesn't look like a vacancy.";
      - the AI could not rate it after 3 attempts: "Jobbi couldn't rate this post."
    - [ ] When the daily limit is reached or the AI is unavailable, the post waits as in spec 009, and the second message comes when it is rated.
    - [ ] Cards from forwarded posts are not included in the combined alert (spec 009 §2.4); the second message replaces it.
    - [ ] A post Jobbi has already seen (forwarded before, or found in a watched channel) gets "Jobbi has already seen this post." and is not rated again. If its card from a watched channel is still waiting to be rated, that card is not alerted later.
    - [ ] A forwarded post without text (media without a caption) gets "This post has no text, so there is nothing to add to the Inbox."
    - [ ] A chat not linked to a Jobbi account gets "🔒 Please link your account first. Send /start and enter your code." and nothing is saved.
    - [ ] Forwards from people or groups, and typed text, keep the tracker dialog of spec 006.
    - [ ] Cards from forwarded posts show the channel title as their source; in the Inbox source filter that channel appears as "<title> (forwarded)".
    - [ ] Only the private chat with the bot is handled; posts sent to the bot in groups or channels are ignored.

### 2.4 Update 2026-11-24: pre-AI keyword filter

Since exclude words were removed (backlog #12), every new post of every source went to the AI, and one noisy channel could use up the AI's free daily quota. The keyword filter is inclusive: a post reaches the AI only if it names at least one of the user's keywords (about 3% of queued posts passed in a measurement).

- **As a** user, **I want to** list words my vacancies always contain, **so that** Jobbi does not spend its daily AI quota on posts that are clearly not for me.
  - **Acceptance Criteria:**
    - [ ] The "What are you looking for?" form in the Sources panel has a **Keywords** list (chips; up to 50, 1–64 characters each with at least one letter or digit; a 51st shows "You can add up to 50 keywords") and a switch **"Only send posts with these words to the AI"** (on by default). Saving stores the description, keywords and switch together; keywords are shown as saved: trimmed, lowercased, without duplicates.
    - [ ] While the switch is on and the list is not empty, a new post (Telegram, career page or web page; after the web page is read) whose title and text contain none of the keywords is skipped: it is not sent to the AI, never shown, and never comes back, even if the keywords change later.
    - [ ] A keyword matches at the start of a word, in any letter case, and also matches longer words ("фронт" finds "фронтенд", "react" finds "reactjs"); "front end" also finds "front-end"; a keyword starting with a symbol also matches inside a word (".net" finds "ASP.NET"). The form shows this hint.
    - [ ] One matching line is enough: a digest naming a keyword once is rated in full (§2.1).
    - [ ] Posts forwarded to the bot (§2.2) are never skipped by the filter. Forwarding a post the filter already skipped rates it like a new forwarded post.
    - [ ] Switch off or an empty list: every new post goes to the AI, as before.
    - [ ] The form shows "Skipped by the filter in the last 24 hours: N".
    - [ ] Keywords and the switch are per user.

Trade-off (option A): a skipped post keeps only its "seen" mark, so adding a keyword later does not bring old skipped posts back. Re-checking skipped posts after a keyword change is backlog #21; an AI-suggested keyword list is backlog #20.

Follow-ups (backlog #19, 2026-11-24):

- Each source row in the Sources panel shows "Waiting for AI: N" (its posts not rated yet, web pages still being read included) when N > 0; it updates with the panel's refresh.
- Stale posts: before rating, a waiting post older than 7 days (Telegram: by its publish time; career pages and web pages: by when Jobbi found it) is dropped without an AI call and never comes back. Posts forwarded to the bot and web pages not read yet are never dropped.

### 2.3 Changes to spec 009

Spec 009 stays Completed. These of its points are superseded by this spec, and 009 gets a pointer next to each:
- §2.2 "Every post … is evaluated by AI" and "Each match gets a fit rating": now per vacancy when a post lists several (§2.1 here).
- §2.2 "A post or job Jobbi has seen before never creates a second card" and "the card keeps the date, fit and text of the first post found": a digest can give several cards, each with its own fragment.
- Terms, "Job link": for a digest it is defined per vacancy.
- Out-of-Scope, "Private Telegram channels and groups": forwarding their posts is now supported (§2.2 here); reading them directly stays out of scope.
- §2.1 exclude words (adding, removing, per user) and §2.2 "contains none of the exclude words": exclude words are hidden and no longer applied (§2.1 here).

---

## 3. Scope and Boundaries

### In-Scope

- Splitting digests from watched Telegram channels and from forwarded posts.
- Hiding and switching off exclude words (stored words are kept).
- The pre-AI keyword filter (§2.4, added 2026-11-24).
- The daily-summary line about posts longer than Jobbi reads.
- The forward-to-Inbox flow, including the bot's second message with the result.
- Pointers in spec 009; roadmap: add the Vacancy Discovery item and update "Quick Add from Telegram" (a forward from a channel now goes to the Inbox).

### Out-of-Scope

- Link-only digests: opening the link and splitting the page behind it (possible later, together with web-page sources of spec 010).
- Splitting career-page jobs (they are always single jobs).
- Re-rating seen posts, re-splitting old cards, re-rating after the search description changes.
- An AI-generated keyword list (backlog #20) and re-checking posts skipped by the keyword filter after the keywords change (backlog #21).
- Reading private channels as the user's own Telegram account; channels with "Restrict saving content" cannot be forwarded at all.
- Managing sources from the bot.
- Other roadmap items: HeadHunter Integration, LinkedIn Integration.
