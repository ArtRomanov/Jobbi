# Product Roadmap: Jobbi

_This roadmap outlines our strategic direction based on user needs and product goals. It focuses on the "what" and "why," not the technical "how."_

---

### Phase 1 — Foundation & Application Tracking

_The core scaffolding: authentication and the application tracker that everything else builds on._

- [x] **User Account Essentials**
  - [x] **Sign-Up & Login:** Allow the user to create an account and sign in securely, providing a personal entry point to Jobbi.
  - [x] **Profile Management:** Enable the user to manage their name, email, and basic job search preferences.

- [x] **Application Tracker**
  - [x] **Kanban Board View:** A drag-and-drop board with columns for each stage: Researching, Applied, Interview, Offer, Rejected, Withdrawn.
  - [x] **Timeline View:** A chronological timeline showing all applications and their status changes over time.
  - [x] **Application Details:** Each application card stores company name, role, link to posting, notes, and status history.

---

### Phase 2 — CV Constructor & AI Assistant

_With tracking in place, add the tools that make each application stronger._

- [x] **CV Constructor**
  - [x] **CV Builder:** Create and edit CVs within Jobbi using a structured form/editor.
  - [x] **Multiple Versions:** Store multiple CV versions and link specific versions to specific job applications.
  - [x] **Tailoring per Role:** Quickly duplicate and adjust a base CV to match a specific job's requirements.

- [x] **AI Chat Integration**
  - [x] **CV Refinement Assistant:** Use AI to review and improve CV content — wording, structure, keyword optimization.
  - [x] **Cover Letter Generation:** Generate tailored cover letters based on the job description and selected CV.
  - [x] **Interview Prep:** Ask the AI assistant for interview questions, company research, and preparation tips relevant to a specific role.

---

### Phase 3 — Metrics & Insights

_Turn tracked data into actionable visibility on the job search._

- [x] **Metrics Dashboard**
  - [x] **Pipeline Overview:** Visual summary of applications by stage — how many in each column at a glance.
  - [x] **Response Rate Tracking:** Track which applications got responses vs. silence, and the average time-to-response.
  - [x] **Trend Charts:** Show application activity and outcomes over time (weekly/monthly).

---

### Phase 4 — Job Search Integrations (V1.1)

_Extend Jobbi with external job sources to streamline the research step._

- [x] **Telegram Bot Integration**
  - [x] **Job Alerts via Telegram:** Receive notifications about new matching jobs directly in Telegram.
  - [x] **Quick Add from Telegram:** Send or forward a job posting to Jobbi's bot to create an application entry automatically. A post forwarded from a channel goes to the Inbox instead (see Vacancy Discovery).

- [ ] **Vacancy Discovery (Inbox)**
  - [x] **Watched Sources & AI Rating:** Jobbi checks the user's public Telegram channels and Greenhouse/Lever career pages every hour, rates new posts against a plain-text search description, and collects matches in an Inbox, with alerts in Telegram (spec 009).
  - [ ] **Digest & Forwarded Posts:** A post that lists several vacancies is split, and only matching vacancies become cards; posts forwarded to the bot from any channel, private ones included, are rated the same way, and the bot reports the result (spec 012).

- [ ] **HeadHunter Integration**
  - [ ] **Job Search & Import:** Search HeadHunter from within Jobbi and import job postings directly as application entries.

- [ ] **LinkedIn Integration**
  - [ ] **LinkedIn Job Feed:** Browse and import LinkedIn job postings into Jobbi's tracker.