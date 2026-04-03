# Functional Specification: Application Tracker

- **Roadmap Item:** Application Tracker (Phase 1 — Foundation & Application Tracking)
- **Status:** Draft
- **Author:** Poe (AI Product Analyst)

---

## 1. Overview and Rationale (The "Why")

The application tracker is the heart of Jobbi. Without it, the user has no central place to manage their job search pipeline — applications are scattered across emails, browser tabs, and spreadsheets.

**Problem:** The user loses track of where they applied, what stage each application is in, and what happened when. There's no single view showing the full picture of their job search.

**Desired outcome:** A visual, interactive board that shows every job application and its current stage at a glance. The user can create applications, drag them between stages, view details in a side panel, and see a chronological timeline of all activity. Every status change is logged automatically to preserve the journey.

**Success criteria:**
- The user can see all active applications organized by stage in under 2 seconds.
- Creating a new application takes less than 30 seconds.
- The full history of any application (status changes, dates) is available with one click.

---

## 2. Functional Requirements (The "What")

### 2.1 Kanban Board View

- **As a** user, **I want to** see all my job applications organized by status columns on a board, **so that** I can instantly understand my pipeline at a glance.
  - **Acceptance Criteria:**
    - [ ] The board displays columns for each status: Researching, Applied, Interview, Offer, Rejected, Withdrawn.
    - [ ] Each application appears as a card showing the company name, role title, and how long ago it was created or last updated.
    - [ ] Cards can be dragged and dropped between columns to change their status. The status update happens immediately (no confirmation dialog).
    - [ ] Dragging a card to a new column automatically logs a status change entry in the application's history.
    - [ ] Empty columns show a visual placeholder indicating no applications in that stage.
    - [ ] A "New Application" button is visible on the board, leading to the dedicated creation page.

### 2.2 Create Application

- **As a** user, **I want to** create a new job application entry, **so that** I can start tracking a position I'm interested in.
  - **Acceptance Criteria:**
    - [ ] A dedicated page for creating a new application is accessible from the board's "New Application" button and from the main navigation.
    - [ ] The form collects: company name (required), role/title (required), job posting URL (optional), salary range min/max (optional), salary currency (optional), contact name (optional), contact email (optional), notes (optional, plain text), and initial status (defaults to "Researching").
    - [ ] On successful creation, the user is redirected back to the kanban board where the new card appears in the appropriate column.
    - [ ] Validation: company name and role are required. If missing, show inline errors.

### 2.3 Application Detail Side Panel

- **As a** user, **I want to** click on an application card to see its full details, **so that** I can review and update information without leaving the board.
  - **Acceptance Criteria:**
    - [ ] Clicking a card on the kanban board opens a side panel (drawer) sliding in from the right. The board remains visible behind the panel.
    - [ ] The side panel displays all application fields: company name, role, job posting URL (as clickable link), salary range, contact name, contact email, notes, current status, created date, and status history.
    - [ ] All fields are editable inline within the side panel (except status history and created date).
    - [ ] Changes are saved with a "Save" button. On success, show a toast: "Application updated."
    - [ ] The status can be changed from a dropdown within the panel (in addition to drag-and-drop on the board).
    - [ ] Status history is displayed as a chronological list: "Status changed to [Stage] — [Date/Time]".
    - [ ] A "Delete" button is available with a confirmation dialog: "Are you sure you want to delete this application? This action cannot be undone." On confirm, the application is deleted and the panel closes.
    - [ ] The panel can be closed by clicking an X button or clicking outside the panel.

### 2.4 Search and Filter

- **As a** user, **I want to** search and filter my applications, **so that** I can quickly find specific entries on a crowded board.
  - **Acceptance Criteria:**
    - [ ] A search bar above the kanban board filters cards by company name or role title as the user types (client-side filtering).
    - [ ] Status column visibility can be toggled — the user can hide/show specific columns (e.g., hide "Rejected" to focus on active applications).
    - [ ] Filters are not persisted — refreshing the page resets to showing all columns with no search query.

### 2.5 Timeline View

- **As a** user, **I want to** see a chronological view of my job search activity, **so that** I can understand the pace and progression of my search over time.
  - **Acceptance Criteria:**
    - [ ] A "Timeline" view toggle is available alongside the kanban board (e.g., tabs: "Board" | "Timeline").
    - [ ] The activity feed section shows a chronological list of all status changes across all applications, newest first: "[Company] — [Role] moved to [Stage] — [Date/Time]".
    - [ ] Below the activity feed, a filterable list shows all applications sorted by last activity date, with company, role, current status, and last updated date visible.
    - [ ] Clicking an application in the timeline list opens the same detail side panel as the kanban board.

---

## 3. Scope and Boundaries

### In-Scope

- Kanban board with 6 status columns and drag-and-drop
- Application creation via dedicated page (company, role, URL, salary, contact, notes, status)
- Application detail side panel with inline editing
- Automatic status change history logging
- Search bar filtering by company/role
- Column visibility toggle
- Timeline view with activity feed and application list
- Delete application with confirmation

### Out-of-Scope

- **User Account Essentials** (completed — Phase 1)
- **CV Constructor** (Phase 2)
- **Claude Chat Integration** (Phase 2)
- **Metrics Dashboard** (Phase 3 — will use application data from this tracker)
- **Telegram/HeadHunter/LinkedIn integrations** (Phase 4)
- Rich text notes (future Phase 5)
- Bulk actions (select multiple, change status, delete)
- Import/export of applications
- Application reminders/follow-up notifications
- Sorting within columns (e.g., by date, by company)
