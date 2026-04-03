<!--
This document describes HOW to build the feature at an architectural level.
It is NOT a copy-paste implementation guide.
-->

# Technical Specification: Application Tracker

- **Functional Specification:** `context/spec/002-application-tracker/functional-spec.md`
- **Status:** Draft
- **Author(s):** Poe (AI Technical Architect)

---

## 1. High-Level Technical Approach

This feature adds the core application tracking functionality to Jobbi. It requires two new database tables (`applications` and `application_status_history`), a full CRUD API with pagination and server-side search under `/api/v1/applications`, and a rich frontend with a drag-and-drop kanban board (@dnd-kit), detail side panel, creation page, search/filter, and timeline view.

The backend follows the existing patterns: SQLAlchemy models, Pydantic schemas, service layer, FastAPI routes. The frontend uses FSD architecture with a new `application` entity, dedicated pages, and feature slices for the board and timeline.

**Systems affected:** New models, migrations, API routes, and frontend pages. Dashboard placeholder is replaced with the kanban board.

---

## 2. Proposed Solution & Implementation Plan

### 2.1 Data Model / Database Changes

**Table: `applications`**

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID (String 36) | PK | Generated server-side |
| `user_id` | UUID (String 36) | FK → users.id, NOT NULL, indexed | Owner |
| `company_name` | VARCHAR(255) | NOT NULL | |
| `role_title` | VARCHAR(255) | NOT NULL | |
| `job_url` | VARCHAR(2048) | NULLABLE | Link to posting |
| `salary_min` | INTEGER | NULLABLE | |
| `salary_max` | INTEGER | NULLABLE | |
| `salary_currency` | VARCHAR(3) | NULLABLE | ISO 4217 |
| `contact_name` | VARCHAR(255) | NULLABLE | Recruiter/contact |
| `contact_email` | VARCHAR(255) | NULLABLE | |
| `notes` | TEXT | NULLABLE | Plain text |
| `status` | VARCHAR(20) | NOT NULL, default "researching" | Enum: researching, applied, interview, offer, rejected, withdrawn |
| `created_at` | DATETIME | NOT NULL | server_default |
| `updated_at` | DATETIME | NOT NULL | server_default, onupdate |

**Table: `application_status_history`**

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID (String 36) | PK | |
| `application_id` | UUID (String 36) | FK → applications.id, NOT NULL, indexed | CASCADE delete |
| `status` | VARCHAR(20) | NOT NULL | The status changed to |
| `changed_at` | DATETIME | NOT NULL | server_default |

**Migration:** Single Alembic migration creates both tables.

### 2.2 API Contracts

**Application CRUD** (all require JWT):

**`GET /api/v1/applications`** — List user's applications (paginated, searchable)
- Query params: `page` (default 1), `per_page` (default 50), `status` (optional filter), `search` (optional — case-insensitive match on company_name or role_title)
- Success (200): `{ items: ApplicationRead[], total: int, page: int, per_page: int }`
- Only returns applications belonging to the current user

**`POST /api/v1/applications`** — Create application
- Request: `{ company_name, role_title, job_url?, salary_min?, salary_max?, salary_currency?, contact_name?, contact_email?, notes?, status? }`
- Success (201): `ApplicationRead` (includes auto-generated initial status history entry)

**`GET /api/v1/applications/{id}`** — Get application with status history
- Success (200): `ApplicationDetailRead` (all fields + `status_history: StatusHistoryRead[]`)
- Error (404): Application not found or doesn't belong to user

**`PATCH /api/v1/applications/{id}`** — Update application
- Request: `{ company_name?, role_title?, job_url?, salary_min?, salary_max?, salary_currency?, contact_name?, contact_email?, notes?, status? }`
- If `status` changes, automatically create a new status history entry
- Success (200): `ApplicationDetailRead`

**`DELETE /api/v1/applications/{id}`** — Delete application
- Cascade deletes status history
- Success (200): `{ message: "Application deleted." }`

**`GET /api/v1/applications/history`** — Get status history feed (for timeline)
- Query params: `page` (default 1), `per_page` (default 50)
- Success (200): `{ items: StatusHistoryFeedRead[], total: int, page: int, per_page: int }`
- Each item includes application company_name and role_title for display

### 2.3 Backend Components

| Path | Responsibility |
|---|---|
| `backend/app/models/application.py` | SQLAlchemy `Application` and `ApplicationStatusHistory` models |
| `backend/app/schemas/application.py` | Pydantic schemas: `ApplicationCreate`, `ApplicationUpdate`, `ApplicationRead`, `ApplicationDetailRead`, `StatusHistoryRead`, `StatusHistoryFeedRead`, `PaginatedResponse` |
| `backend/app/services/application_service.py` | CRUD business logic: list (with search/filter/pagination), create (with initial history), get, update (with status change detection), delete, history feed |
| `backend/app/api/v1/applications.py` | Route handlers for all application endpoints |

### 2.4 Frontend Components (FSD)

| Layer/Slice | Path | Content |
|---|---|---|
| `entities/application` | `frontend/src/entities/application/` | Application and StatusHistory types, API calls (list, create, get, update, delete, history), barrel export |
| `features/kanban-board` | `frontend/src/features/kanban-board/` | KanbanBoard component with @dnd-kit drag-and-drop, KanbanColumn, ApplicationCard, drag handlers that call PATCH on status change |
| `features/application-panel` | `frontend/src/features/application-panel/` | Side panel (drawer) component for viewing/editing application details, delete with confirmation |
| `features/timeline-feed` | `frontend/src/features/timeline-feed/` | Timeline activity feed and application list components |
| `pages/dashboard` | `frontend/src/pages/dashboard/` | Replace placeholder with Board/Timeline tab toggle, search bar (debounced, sends query to API), column visibility toggles |
| `pages/new-application` | `frontend/src/pages/new-application/` | Application creation form page (React Hook Form + Zod) |

### 2.5 Frontend Libraries

| Library | Purpose |
|---|---|
| `@dnd-kit/core` | Drag-and-drop engine |
| `@dnd-kit/sortable` | Sortable list primitives for kanban columns |
| `@dnd-kit/utilities` | CSS transform utilities |
| `openapi-typescript` | Generate TypeScript types from FastAPI's OpenAPI spec (dev dependency) |

### 2.6 OpenAPI Type Generation

**Single source of truth:** Pydantic schemas on the backend define all API types. TypeScript types are auto-generated from FastAPI's OpenAPI spec — no manual type duplication.

**Setup:**
- Install `openapi-typescript` as a dev dependency in the frontend
- Add a `pnpm generate:types` script that fetches `http://localhost:8000/openapi.json` and generates `frontend/src/shared/api/schema.d.ts`
- The generated file is committed to the repo (so builds work without the backend running)
- Existing manually-defined entity types (e.g., `entities/user/model/types.ts`) should be migrated to use generated types or re-exported from the generated file

**Workflow:**
1. Developer changes a Pydantic schema on the backend
2. Runs `pnpm generate:types` in the frontend
3. TypeScript compiler catches any mismatches immediately

### 2.7 Configuration

No new environment variables needed. All endpoints use existing JWT auth and database.

---

## 3. Impact and Risk Analysis

**System Dependencies:**
- Depends on the auth system (JWT + user_id) from User Account Essentials
- The Metrics Dashboard (Phase 3) will query these tables for stats

**Potential Risks & Mitigations:**

| Risk | Impact | Mitigation |
|---|---|---|
| Drag-and-drop performance with many cards | Sluggish UX | @dnd-kit is lightweight. For 100+ cards per column, consider virtualization later. |
| Optimistic updates on drag causing stale state | UI/data mismatch | Update UI immediately, roll back on API error with toast notification. |
| CASCADE delete removing history | Data loss | Intentional — deleting an application removes all its history. Confirmation dialog prevents accidental deletion. |
| Server-side search latency | Slow search | Debounce frontend search input (300ms). SQLite LIKE queries are fast for small datasets. Add indexes if needed later. |

---

## 4. Testing Strategy

**Backend (pytest):**
- CRUD integration tests for all application endpoints
- Status history auto-creation on create and status change
- Pagination and search tests
- Authorization tests (can't access other user's applications)
- CASCADE delete test

**Frontend (Vitest + Testing Library):**
- Kanban board rendering with cards in correct columns
- Drag-and-drop status change (mock @dnd-kit events)
- Side panel open/close, form editing
- Application creation form validation and submission
- Search bar debounce and API call
- Timeline view rendering
