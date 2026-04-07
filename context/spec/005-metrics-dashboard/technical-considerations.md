<!--
This document describes HOW to build the feature at an architectural level.
It is NOT a copy-paste implementation guide.
-->

# Technical Specification: Metrics Dashboard

- **Functional Specification:** `context/spec/005-metrics-dashboard/functional-spec.md`
- **Status:** Draft
- **Author(s):** Poe (AI Technical Architect)

---

## 1. High-Level Technical Approach

This feature adds a metrics dashboard that aggregates application data and renders KPIs, a pipeline overview, and a trend chart. No new tables — all metrics are computed from the existing `applications` and `application_status_history` tables.

The backend exposes a single `GET /api/v1/metrics` endpoint that accepts a date range and returns all metrics in one response. The frontend uses **Recharts** to render the trend line chart.

**Systems affected:** New backend metrics service + endpoint, new frontend page + entity slice + Recharts dependency, navigation update.

---

## 2. Proposed Solution & Implementation Plan

### 2.1 Data Model / Database Changes

**No schema changes.** All metrics are computed from existing tables:
- `applications` — for KPI counts, pipeline counts, trend data points
- `application_status_history` — for response rate detection (did the app ever reach Interview/Offer/Rejected?)

### 2.2 API Contracts

**`GET /api/v1/metrics`** — Aggregated metrics for the user
- Query params:
  - `range`: enum string — `"7d"`, `"30d"`, `"90d"`, `"all"` (default: `"30d"`)
- Success (200):
```json
{
  "range": "30d",
  "from_date": "2026-03-08",
  "to_date": "2026-04-07",
  "kpis": {
    "total_applications": 42,
    "active": 28,
    "response_rate": 0.35,
    "interviews": 12
  },
  "pipeline": [
    { "status": "researching", "count": 5 },
    { "status": "applied", "count": 11 },
    { "status": "interview", "count": 8 },
    { "status": "offer", "count": 2 },
    { "status": "rejected", "count": 14 },
    { "status": "withdrawn", "count": 2 }
  ],
  "trend": {
    "granularity": "daily",
    "points": [
      { "date": "2026-03-08", "count": 2 },
      { "date": "2026-03-09", "count": 0 },
      ...
    ]
  }
}
```

### 2.3 Backend Components

| Path | Responsibility |
|---|---|
| `backend/app/schemas/metrics.py` | Pydantic schemas: `MetricsResponse`, `KpiData`, `PipelineEntry`, `TrendData`, `TrendPoint` |
| `backend/app/services/metrics_service.py` | Aggregation logic: compute KPIs, pipeline counts, trend data points; date range resolution; granularity selection |
| `backend/app/api/v1/metrics.py` | Single route handler for `GET /metrics` |

### 2.4 Metrics Computation Logic

**KPIs (filtered by date range on `created_at`):**
- `total_applications`: COUNT(*) where created_at in range
- `active`: COUNT(*) where created_at in range AND status NOT IN ('rejected', 'withdrawn')
- `response_rate`: For each application created in range, check if `application_status_history` ever contains a row with status IN ('interview', 'offer', 'rejected'). Count those, divide by total. Excludes Withdrawn from numerator.
- `interviews`: COUNT(*) of applications created in range that ever reached 'interview' status (via status_history)

**Pipeline:** GROUP BY status, COUNT(*) for applications created in range. Always return all 6 statuses (zero-fill missing).

**Trend:** GROUP BY date_trunc(granularity, created_at), COUNT(*).
- Granularity selection:
  - `7d` → daily (7 buckets)
  - `30d` → daily (30 buckets)
  - `90d` → weekly (~13 buckets)
  - `all` → weekly if range < 1 year, otherwise monthly
- Zero-fill missing dates so the chart has continuous data.

**Date range resolution:**
- `7d` → from = today - 7 days, to = today
- `30d` → from = today - 30 days, to = today
- `90d` → from = today - 90 days, to = today
- `all` → from = earliest application created_at (or today if none), to = today

### 2.5 Frontend Components (FSD)

| Layer/Slice | Path | Content |
|---|---|---|
| `entities/metrics` | `frontend/src/entities/metrics/` | Metrics types (from OpenAPI), API call: `getMetrics(range)` |
| `features/metrics-dashboard` | `frontend/src/features/metrics-dashboard/` | `KpiCards` component, `PipelineOverview` component, `TrendChart` component (uses Recharts), `DateRangeSelector` component |
| `pages/metrics` | `frontend/src/pages/metrics/` | The metrics page composing all metric sections |

Modified:
| Layer/Slice | Change |
|---|---|
| `app/router` | Add `/metrics` route (protected) |
| `app/layout` | Add "Metrics" link to navigation |

### 2.6 Frontend Libraries

| Library | Purpose |
|---|---|
| `recharts` | Declarative React charting library for the trend line chart |

### 2.7 Configuration

No new environment variables needed.

---

## 3. Impact and Risk Analysis

**System Dependencies:**
- Reads from `applications` and `application_status_history` tables (no writes)
- Phase 4 features (job integrations) won't affect metrics — they'll just create more applications

**Potential Risks & Mitigations:**

| Risk | Impact | Mitigation |
|---|---|---|
| Slow aggregation queries on large datasets | Slow page load | SQLite is fast for thousands of rows. Personal app — no pagination needed. Indexes on `user_id` and `created_at` already exist. |
| Recharts bundle size (~100KB) | Larger frontend bundle | Acceptable trade-off for a quality charting library. Lazy-load the metrics page if needed. |
| Date math timezone issues | Wrong day buckets | Use UTC dates throughout. Format on frontend for display. |
| Empty data state | Charts look broken | Show explicit empty state message instead of empty chart. |

---

## 4. Testing Strategy

**Backend (pytest):**
- KPI calculations: total, active, response rate, interviews — verify with seeded data
- Pipeline aggregation: all 6 statuses present, correct counts
- Trend granularity selection: 7d → daily, 90d → weekly
- Date range filtering: applications outside range excluded
- Empty state: no applications → all zeros
- Response rate calculation: correctly counts apps that reached Interview/Offer/Rejected via status history

**Frontend (Vitest + Testing Library):**
- Metrics page renders KPI cards with values
- Date range selector switches active range
- Pipeline overview shows all statuses
- Empty state message when no data
- Mock the chart component (Recharts is hard to test directly)
