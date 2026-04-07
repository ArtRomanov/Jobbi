# Tasks: Metrics Dashboard

---

- [x] **Slice 1: Metrics aggregation API**
  - [x] Create Pydantic schemas: `KpiData`, `PipelineEntry`, `TrendPoint`, `TrendData`, `MetricsResponse`. **[Agent: python-backend]**
  - [x] Create `metrics_service.py`: date range resolution, KPI calculation (total, active, response rate via status_history join, interviews), pipeline aggregation by status (zero-fill all 6 statuses), trend bucketing with adaptive granularity (daily/weekly/monthly). **[Agent: python-backend]**
  - [x] Create `GET /api/v1/metrics?range=7d|30d|90d|all` route. Mount in v1 router. **[Agent: python-backend]**
  - [x] Verify: curl with each range — returns kpis, pipeline (6 statuses), trend points. Empty state returns zeros. **[Agent: qa-tester]**

---

- [ ] **Slice 2: Metrics dashboard UI**
  - [ ] Install `recharts`. Regenerate OpenAPI types. Create `entities/metrics/` slice: types from generated schema, `getMetrics(range)` API call. **[Agent: typescript-frontend]**
  - [ ] Create `features/metrics-dashboard/` slice: `DateRangeSelector` (4 preset buttons), `KpiCards` (4 cards), `PipelineOverview` (status bars with theme colors), `TrendChart` (Recharts line chart). FSD-compliant — constants in `lib/`, no logic in UI files. **[Agent: typescript-frontend]**
  - [ ] Create `pages/metrics/` page: composes all sections, manages selected range state, fetches metrics on range change, shows loading and empty states. **[Agent: typescript-frontend]**
  - [ ] Add `/metrics` route (protected) to router. Add "Metrics" link to navigation. **[Agent: typescript-frontend]**
  - [ ] Code review: Review chart integration, FSD compliance, and theme usage. **[Agent: react-code-reviewer]**
  - [ ] Verify: Navigate to /metrics → see KPIs, pipeline, trend chart. Switch date range → all metrics update. Empty state shown when no data. **[Agent: qa-tester]**

---

- [ ] **Slice 3: Backend test suite for metrics**
  - [ ] KPI calculation tests: total, active, interviews counts with seeded data. **[Agent: python-backend]**
  - [ ] Response rate test: applications that reached Interview/Offer/Rejected counted; Withdrawn excluded. **[Agent: python-backend]**
  - [ ] Pipeline aggregation test: all 6 statuses present even when count is 0. **[Agent: python-backend]**
  - [ ] Trend granularity test: 7d→daily, 90d→weekly. Verify date bucketing. **[Agent: python-backend]**
  - [ ] Date range filter test: applications outside range excluded. **[Agent: python-backend]**
  - [ ] Authorization test: only the user's own applications counted. **[Agent: python-backend]**
  - [ ] Verify: `pytest` runs all tests — 100% pass rate. **[Agent: qa-tester]**

---

- [ ] **Slice 4: Frontend test suite for metrics**
  - [ ] Add MSW handler for `GET /metrics` returning mock data. **[Agent: typescript-frontend]**
  - [ ] Metrics page tests: renders KPI values, renders all 6 pipeline statuses. **[Agent: typescript-frontend]**
  - [ ] Date range selector tests: 4 buttons, click changes active state, triggers re-fetch. **[Agent: typescript-frontend]**
  - [ ] Empty state test: zero data → empty message displayed. **[Agent: typescript-frontend]**
  - [ ] Code review: Review test patterns and chart mocking. **[Agent: react-code-reviewer]**
  - [ ] Verify: `pnpm test` runs all tests — 100% pass rate. **[Agent: qa-tester]**
