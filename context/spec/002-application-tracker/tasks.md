# Tasks: Application Tracker

---

- [x] **Slice 1: OpenAPI type generation pipeline**
  - [x] Install `openapi-typescript` as dev dependency. Add `pnpm generate:types` script that fetches `http://localhost:8000/openapi.json` and outputs `frontend/src/shared/api/schema.d.ts`. **[Agent: typescript-frontend]**
  - [x] Generate initial types from current API (auth + user endpoints). Migrate `entities/user/model/types.ts` to re-export from generated schema. **[Agent: typescript-frontend]**
  - [x] Verify: `pnpm generate:types` runs without errors, `pnpm run build` passes, existing user entity still works. **[Agent: qa-tester]**

---

- [x] **Slice 2: Application CRUD API**
  - [x] Create `Application` and `ApplicationStatusHistory` SQLAlchemy models. Create Alembic migration for both tables. **[Agent: database-expert]**
  - [x] Create Pydantic schemas: `ApplicationCreate`, `ApplicationUpdate`, `ApplicationRead`, `ApplicationDetailRead`, `StatusHistoryRead`, `StatusHistoryFeedRead`, `PaginatedResponse`. **[Agent: python-backend]**
  - [x] Implement `application_service.py`: list (paginated, searchable, filterable), create (with initial status history), get (with history), update (with status change detection → auto-log history), delete (cascade). **[Agent: python-backend]**
  - [x] Implement all application API routes: `GET /applications`, `POST /applications`, `GET /applications/{id}`, `PATCH /applications/{id}`, `DELETE /applications/{id}`, `GET /applications/history`. Mount in v1 router. **[Agent: python-backend]**
  - [x] Verify: curl all endpoints — create application (201), list with pagination (200), get with history (200), update status and verify history entry created, search by company name, delete (200). **[Agent: qa-tester]**

---

- [x] **Slice 3: Create application via dedicated page**
  - [x] Regenerate OpenAPI types to include new application schemas. Create `entities/application/` slice with types re-exported from generated schema, API calls (list, create, get, update, delete, history). **[Agent: typescript-frontend]**
  - [x] Create `pages/new-application/` page: form with company name, role title, URL, salary, contact, notes, initial status dropdown. React Hook Form + Zod. On success → redirect to dashboard. **[Agent: typescript-frontend]**
  - [x] Add `/new-application` route (protected) to router. Add "New Application" link to navigation. **[Agent: typescript-frontend]**
  - [x] Code review: Review application entity and creation page for FSD compliance, form patterns, and type usage. **[Agent: react-code-reviewer]**
  - [x] Verify: Navigate to new application page → fill form → submit → application created (verify via curl GET). **[Agent: qa-tester]**

---

- [ ] **Slice 4: Kanban board with drag-and-drop**
  - [ ] Install `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`. **[Agent: typescript-frontend]**
  - [ ] Create `features/kanban-board/` slice: `KanbanBoard` component (fetches all applications, groups by status), `KanbanColumn` (renders column header + cards), `ApplicationCard` (shows company, role, time since update). **[Agent: typescript-frontend]**
  - [ ] Implement drag-and-drop: dragging a card between columns calls `PATCH /applications/{id}` with new status. Optimistic UI update — roll back on error with toast. **[Agent: typescript-frontend]**
  - [ ] Replace dashboard placeholder with `KanbanBoard`. Show "New Application" button on the board. **[Agent: typescript-frontend]**
  - [ ] Code review: Review kanban board for @dnd-kit patterns, optimistic updates, FSD compliance, and performance. **[Agent: react-code-reviewer]**
  - [ ] Verify: Dashboard shows kanban board with 6 columns. Create an application → card appears in correct column. Drag card to new column → status updates (verify via curl). **[Agent: qa-tester]**

---

- [ ] **Slice 5: Detail side panel with editing**
  - [ ] Create `features/application-panel/` slice: `ApplicationPanel` drawer component. Fetches application detail (with status history) on open. Displays all fields, status history log. **[Agent: typescript-frontend]**
  - [ ] Add inline editing: editable form fields, status dropdown, "Save" button (PATCH), "Delete" button with confirmation dialog. **[Agent: typescript-frontend]**
  - [ ] Wire panel to kanban board: clicking a card opens the panel. Panel close on X or click outside. Board refreshes data after save/delete. **[Agent: typescript-frontend]**
  - [ ] Code review: Review side panel for accessibility (focus trap, escape key), form patterns, and FSD compliance. **[Agent: react-code-reviewer]**
  - [ ] Verify: Click card → panel opens with correct data. Edit a field → save → panel shows updated data. Change status via dropdown → history entry appears. Delete → card removed from board. **[Agent: qa-tester]**

---

- [ ] **Slice 6: Search and column filter**
  - [ ] Add search bar above the board: debounced input (300ms) that calls `GET /applications?search=...`. Board re-renders with filtered results. **[Agent: typescript-frontend]**
  - [ ] Add column visibility toggles: checkboxes or toggle buttons to show/hide specific status columns. State is local (not persisted). **[Agent: typescript-frontend]**
  - [ ] Code review: Review search debounce pattern, filter UX, and re-render performance. **[Agent: react-code-reviewer]**
  - [ ] Verify: Type in search → board shows only matching cards. Toggle off "Rejected" column → column hidden. Refresh page → filters reset. **[Agent: qa-tester]**

---

- [ ] **Slice 7: Timeline view**
  - [ ] Create `features/timeline-feed/` slice: `ActivityFeed` component (fetches `GET /applications/history`, renders chronological status change entries), `ApplicationList` component (filterable list of all applications sorted by last activity). **[Agent: typescript-frontend]**
  - [ ] Add Board/Timeline tab toggle to the dashboard page. Timeline tab shows ActivityFeed + ApplicationList. **[Agent: typescript-frontend]**
  - [ ] Wire timeline: clicking an application in the list opens the same detail side panel as the kanban board. **[Agent: typescript-frontend]**
  - [ ] Code review: Review timeline components for pagination, FSD compliance, and shared panel reuse. **[Agent: react-code-reviewer]**
  - [ ] Verify: Switch to Timeline tab → see status change feed. Click an application → panel opens. Create/update applications → timeline reflects changes. **[Agent: qa-tester]**

---

- [ ] **Slice 8: Backend test suite for application tracker**
  - [ ] Integration tests for application CRUD: create, list (paginated), get with history, update, delete (cascade). **[Agent: python-backend]**
  - [ ] Tests for status history: auto-created on create, auto-logged on status change, included in detail response. **[Agent: python-backend]**
  - [ ] Tests for search and filter: search by company/role, filter by status, pagination params. **[Agent: python-backend]**
  - [ ] Authorization tests: user can't access/modify another user's applications (404). **[Agent: python-backend]**
  - [ ] Verify: `pytest` runs all tests — 100% pass rate. **[Agent: qa-tester]**

---

- [ ] **Slice 9: Frontend test suite for application tracker**
  - [ ] Add MSW handlers for all application API endpoints. **[Agent: typescript-frontend]**
  - [ ] Kanban board tests: renders columns, cards in correct columns, drag-and-drop status change. **[Agent: typescript-frontend]**
  - [ ] Application creation form tests: validation, successful submission. **[Agent: typescript-frontend]**
  - [ ] Side panel tests: opens on card click, displays data, save and delete actions. **[Agent: typescript-frontend]**
  - [ ] Code review: Review test code for testing best practices and proper async patterns. **[Agent: react-code-reviewer]**
  - [ ] Verify: `pnpm test` runs all tests — 100% pass rate. **[Agent: qa-tester]**