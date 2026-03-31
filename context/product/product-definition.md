# Product Definition: Jobbi

- **Version:** 1.0
- **Status:** Proposed

---

## 1. The Big Picture (The "Why")

### 1.1. Project Vision & Purpose

To give job seekers a friendly, all-in-one personal assistant that eliminates the chaos of scattered spreadsheets, docs, and browser tabs — making the entire job search process organized, visible, and efficient. Jobbi is your small eager buddy that helps you research, tailor, apply, and track your way to your next role.

### 1.2. Target Audience

The primary user is the product creator — a tech professional actively searching for jobs who needs a centralized personal tool to manage the full job search lifecycle, from research to offer.

### 1.3. User Personas

- **Persona 1: "The Active Seeker"**
  - **Role:** A professional actively job hunting across multiple platforms (LinkedIn, HeadHunter, Telegram channels).
  - **Goal:** Wants a single place to track every application, tailor CVs per role, and see clear metrics on how the search is going — without juggling spreadsheets and scattered notes.
  - **Frustration:** Loses track of where they applied, wastes time re-tailoring CVs from scratch, and has no visibility into response rates or pipeline health.

### 1.4. Success Metrics

- **Single source of truth:** The app fully replaces spreadsheets, docs, and ad-hoc notes for job search tracking.
- **Time saved:** CV tailoring per application takes significantly less time with AI assistance and reusable templates.
- **Clear progress visibility:** At any moment, a glance at the dashboard shows pipeline health — applications sent, response rates, and stage distribution.
- **Better application quality:** Tailored CVs and AI-assisted prep lead to improved response rates over time.

---

## 2. The Product Experience (The "What")

### 2.1. Core Features

- **Application Tracker** — A timeline/kanban board to manage job applications through stages: Researching, Applied, Interview, Offer, Rejected, Withdrawn.
- **CV Constructor** — Build, store, and tailor multiple CV versions. Adjust each CV to match specific job requirements.
- **Claude Chat Integration** — An AI assistant (powered by Claude) to help write cover letters, refine CVs, prepare for interviews, and provide job search advice.
- **Metrics Dashboard** — Visual stats on applications sent, response rates, time-to-response, pipeline distribution, and trends over time.

### 2.2. User Journey

1. **Research:** The user finds a new job posting that matches their criteria.
2. **Prepare:** They open Jobbi, create a new application entry, and use the CV Constructor (with Claude's help) to tailor their CV to the specific role's requirements.
3. **Apply:** They submit the application and update the status in Jobbi to "Applied."
4. **Track:** The application appears on their timeline/kanban board. They can add notes, set follow-up reminders, and update the stage as it progresses (Interview, Offer, etc.).
5. **Review:** They check the Metrics Dashboard to see how their job search is performing — how many applications are out, what their response rate looks like, and where to adjust their strategy.

---

## 3. Project Boundaries

### 3.1. What's In-Scope for V1

- User authentication and personal account.
- Application tracker with kanban/timeline view and status management (Researching, Applied, Interview, Offer, Rejected, Withdrawn).
- CV constructor with the ability to create, store, and edit multiple CV versions.
- Claude chat integration for CV refinement, cover letter writing, and interview prep.
- Metrics dashboard showing application counts, response rates, and pipeline health.
- Web application (responsive, desktop-first).

### 3.2. What's Out-of-Scope (V1.1 and Beyond)

- **V1.1 — Job Search Integrations:**
  - Telegram bot integration for job alerts and notifications.
  - HeadHunter API integration for job search and import.
  - LinkedIn job search integration.
- **Future:**
  - Mobile application.
  - Multi-user / team features.
  - Calendar integration for interview scheduling.
  - Automated follow-up reminders.
  - Job posting scraping or aggregation from additional platforms.