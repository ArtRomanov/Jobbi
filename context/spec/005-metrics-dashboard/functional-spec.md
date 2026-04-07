# Functional Specification: Metrics Dashboard

- **Roadmap Item:** Metrics Dashboard (Phase 3 — Metrics & Insights)
- **Status:** Completed
- **Author:** Poe (AI Product Analyst)

---

## 1. Overview and Rationale (The "Why")

After tracking applications and using AI to refine materials, the user needs to step back and see the big picture: How many applications are out? What's working? Are responses speeding up or slowing down?

**Problem:** The user has data in Jobbi but no analytical view. They can see individual cards on the kanban board, but can't answer questions like "What's my response rate this month?" or "Am I sending out more applications than last week?"

**Desired outcome:** A dedicated Metrics page with at-a-glance KPI cards, a pipeline overview by status, and a trend chart showing application activity over time. The user can switch time ranges and instantly understand their job search velocity, conversion, and pipeline health.

**Success criteria:**
- The user can see total applications, active count, response rate, and interview count in under 3 seconds.
- Switching the date range updates all metrics consistently.
- The trend chart clearly shows whether the user is sending more or fewer applications over time.

---

## 2. Functional Requirements (The "What")

### 2.1 Metrics Page Layout

- **As a** user, **I want to** see all my key job search metrics on one page, **so that** I can quickly assess my progress and adjust strategy.
  - **Acceptance Criteria:**
    - [x] A "Metrics" link in the main navigation bar leads to a dedicated metrics page.
    - [x] The page has three sections: KPI cards (top), Pipeline overview (middle), Trend chart (bottom).
    - [x] A date range selector at the top of the page offers preset ranges: "Last 7 days", "Last 30 days", "Last 90 days", "All time". Default: "Last 30 days".
    - [x] Changing the date range updates all metrics on the page (KPI cards, pipeline, trend).
    - [x] The page shows a loading state while metrics are being fetched.
    - [x] If there are no applications in the selected range, an empty state message is shown.

### 2.2 KPI Cards

- **As a** user, **I want to** see headline metrics at a glance, **so that** I instantly know my key numbers.
  - **Acceptance Criteria:**
    - [x] Four KPI cards are displayed in a horizontal row at the top of the page:
      - **Total Applications** — Count of all applications in the selected date range.
      - **Active** — Count of applications NOT in "Rejected" or "Withdrawn" status (in the selected range).
      - **Response Rate** — Percentage of applications that reached "Interview", "Offer", or "Rejected" status, divided by total applications. Excludes "Withdrawn" from numerator (user-initiated, not a response).
      - **Interviews** — Count of applications currently in or that have reached the "Interview" status.
    - [x] Each card shows the label and the numeric value (or percentage for Response Rate).
    - [x] Cards have visual emphasis (large numbers, clean layout).

### 2.3 Pipeline Overview

- **As a** user, **I want to** see how my applications are distributed across stages, **so that** I can identify bottlenecks in my pipeline.
  - **Acceptance Criteria:**
    - [x] A pipeline section shows the count of applications in each status: Researching, Applied, Interview, Offer, Rejected, Withdrawn.
    - [x] Each status is displayed as a bar or column with the count and the status name.
    - [x] Each status uses its color from the theme (matching the kanban board status colors).
    - [x] Status counts respect the selected date range (count of applications created in that range).
    - [x] Empty statuses (count = 0) are still shown for completeness.

### 2.4 Trend Chart

- **As a** user, **I want to** see my application activity over time, **so that** I can understand whether my job search velocity is increasing or decreasing.
  - **Acceptance Criteria:**
    - [x] A line chart shows the number of applications created per day (or per week for longer ranges) over the selected date range.
    - [x] The X-axis shows dates and the Y-axis shows application count.
    - [x] The chart auto-adjusts granularity: daily for "Last 7 days" and "Last 30 days", weekly for "Last 90 days", and weekly or monthly for "All time".
    - [x] Hovering over a point shows the exact date and count (tooltip).
    - [x] If there is no data in the range, a message like "No applications in this period" is shown instead of an empty chart.

---

## 3. Scope and Boundaries

### In-Scope

- Dedicated `/metrics` page accessible from main navigation
- Date range selector with 4 presets (7d / 30d / 90d / All time)
- 4 KPI cards: Total, Active, Response Rate, Interviews
- Pipeline overview by status with counts and theme colors
- Trend line chart showing applications over time with adaptive granularity
- All metrics filtered by the selected date range
- Backend metrics endpoint that returns aggregated data

### Out-of-Scope

- **User Account Essentials** (completed — Phase 1)
- **Application Tracker** (completed — Phase 1)
- **CV Constructor** (completed — Phase 2)
- **Claude Chat Integration** (completed — Phase 2)
- **Telegram/HeadHunter/LinkedIn integrations** (Phase 4)
- Custom date range picker (presets only for V1)
- Comparison views (e.g., this month vs. last month)
- Per-status filter (only date range filter for V1)
- Stacked area or bar charts (only line chart for trends in V1)
- Average time to response (deferred — requires more complex date math)
- Export metrics to CSV/PDF
- Email/notification reports
- Per-company or per-role breakdowns
