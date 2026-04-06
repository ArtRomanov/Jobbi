<!--
This document describes HOW to build the feature at an architectural level.
It is NOT a copy-paste implementation guide.
-->

# Technical Specification: CV Constructor

- **Functional Specification:** `context/spec/003-cv-constructor/functional-spec.md`
- **Status:** Draft
- **Author(s):** Poe (AI Technical Architect)

---

## 1. High-Level Technical Approach

This feature adds CV management to Jobbi. It requires a new `cvs` table (with JSON columns for structured sections), a CRUD API under `/api/v1/cvs`, a link from applications to CVs via a new `cv_id` foreign key, and frontend pages for CV list, editor, and PDF export.

The data model uses **JSON columns** for work experience, education, and other multi-entry sections — keeping the schema simple (one table, no child tables). PDF generation happens **client-side** using `@react-pdf/renderer`.

**Systems affected:** New CV model + migration, new API routes, new frontend pages/features, modification to Application model (add `cv_id` FK) and application panel (add CV linking UI).

---

## 2. Proposed Solution & Implementation Plan

### 2.1 Data Model / Database Changes

**Table: `cvs`**

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID (String 36) | PK | Generated server-side |
| `user_id` | UUID (String 36) | FK → users.id, NOT NULL, indexed | Owner |
| `name` | VARCHAR(255) | NOT NULL | User-defined label (e.g., "Base CV") |
| `personal_info` | JSON | NULLABLE | `{ full_name, email, phone, location, linkedin_url }` |
| `summary` | TEXT | NULLABLE | Professional summary free text |
| `work_experience` | JSON | NULLABLE | Array of `{ company, role, start_date, end_date, is_current, description }` |
| `education` | JSON | NULLABLE | Array of `{ institution, degree, field_of_study, start_year, end_year, description }` |
| `skills` | TEXT | NULLABLE | Free text |
| `languages` | TEXT | NULLABLE | Free text |
| `created_at` | DATETIME | NOT NULL | server_default |
| `updated_at` | DATETIME | NOT NULL | server_default, onupdate |

**Modify table: `applications`**

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `cv_id` | UUID (String 36) | FK → cvs.id, NULLABLE, indexed | SET NULL on CV delete |

**Migrations:** Two Alembic migrations — (1) create `cvs` table, (2) add `cv_id` column to `applications`.

### 2.2 API Contracts

**CV CRUD** (all require JWT):

**`GET /api/v1/cvs`** — List user's CVs
- Success (200): `CvRead[]` (each includes `linked_applications_count`)

**`POST /api/v1/cvs`** — Create CV
- Request: `CvCreate { name, personal_info?, summary?, work_experience?, education?, skills?, languages? }`
- Success (201): `CvRead`

**`GET /api/v1/cvs/{id}`** — Get CV detail
- Success (200): `CvRead`
- Error (404)

**`PATCH /api/v1/cvs/{id}`** — Update CV
- Request: `CvUpdate` (all fields optional)
- Success (200): `CvRead`

**`DELETE /api/v1/cvs/{id}`** — Delete CV
- SET NULL on linked applications' `cv_id`
- Success (200): `{ message: "CV deleted." }`

**`POST /api/v1/cvs/{id}/duplicate`** — Duplicate CV
- Request: `{ name?: string }` (optional custom name, defaults to "[Original] (copy)")
- Success (201): `CvRead` (the new copy)

**Application CV linking** (extend existing endpoints):

**`PATCH /api/v1/applications/{id}`** — now accepts `cv_id` field
- `{ cv_id: "uuid" }` to link, `{ cv_id: null }` to unlink

**`GET /api/v1/applications/{id}`** — now includes `cv_id` and `cv_name` in response

### 2.3 Backend Components

| Path | Responsibility |
|---|---|
| `backend/app/models/cv.py` | SQLAlchemy `Cv` model with JSON columns |
| `backend/app/schemas/cv.py` | Pydantic schemas: `CvCreate`, `CvUpdate`, `CvRead`, `PersonalInfo`, `WorkExperienceEntry`, `EducationEntry` |
| `backend/app/services/cv_service.py` | CRUD business logic: list, create, get, update, delete, duplicate |
| `backend/app/api/v1/cvs.py` | Route handlers for all CV endpoints |

Modified:
| Path | Change |
|---|---|
| `backend/app/models/application.py` | Add `cv_id` FK column + relationship |
| `backend/app/schemas/application.py` | Add `cv_id` and `cv_name` to read schemas, `cv_id` to update schema |
| `backend/app/services/application_service.py` | Include CV name in application responses |

### 2.4 Frontend Components (FSD)

| Layer/Slice | Path | Content |
|---|---|---|
| `entities/cv` | `frontend/src/entities/cv/` | CV types (from OpenAPI schema), API calls (list, create, get, update, delete, duplicate), barrel export |
| `features/cv-editor` | `frontend/src/features/cv-editor/` | CV editor form component with dynamic work experience/education entry management |
| `features/cv-pdf` | `frontend/src/features/cv-pdf/` | PDF document component using @react-pdf/renderer, download trigger |
| `pages/cvs` | `frontend/src/pages/cvs/` | CV list page |
| `pages/cv-editor` | `frontend/src/pages/cv-editor/` | CV create/edit page (wraps cv-editor feature) |

Modified:
| Layer/Slice | Change |
|---|---|
| `features/application-panel` | Add CV section: linked CV display, link/unlink dropdown, "Duplicate & Customize" button |
| `app/router` | Add `/cvs` and `/cvs/:id/edit` routes |
| `app/layout` | Add "CVs" link to navigation |

### 2.5 Frontend Libraries

| Library | Purpose |
|---|---|
| `@react-pdf/renderer` | Client-side PDF generation from React components |

### 2.6 JSON Column Schemas (Pydantic)

Nested Pydantic models for JSON column validation:

```
PersonalInfo { full_name?, email?, phone?, location?, linkedin_url? }
WorkExperienceEntry { company, role, start_date, end_date?, is_current: bool, description? }
EducationEntry { institution, degree?, field_of_study?, start_year?, end_year?, description? }
```

These validate the JSON structure on create/update. Stored as JSON in SQLite (using SQLAlchemy's `JSON` type).

### 2.7 Configuration

No new environment variables needed.

---

## 3. Impact and Risk Analysis

**System Dependencies:**
- Modifies the Application model (adds `cv_id` FK) — requires migration on existing data
- The Claude Chat Integration (next Phase 2 feature) will need access to CV data for refinement

**Potential Risks & Mitigations:**

| Risk | Impact | Mitigation |
|---|---|---|
| JSON columns not queryable | Can't filter CVs by content | Acceptable — we only query by user_id and id. Content search is not in scope. |
| @react-pdf/renderer bundle size | Larger frontend bundle | Lazy-load the PDF feature — only import when user clicks "Download PDF". |
| Duplicate CV with many entries | Slow duplication | JSON copy is instant — no child table joins needed. |
| SET NULL on CV delete | Applications lose CV link silently | Confirmation dialog warns user. Applications show "No CV linked" after deletion. |

---

## 4. Testing Strategy

**Backend (pytest):**
- CV CRUD tests: create, list, get, update, delete
- Duplicate CV test
- Application CV linking: link, unlink, CV name in application response
- SET NULL cascade on CV delete
- JSON column validation (invalid work_experience structure rejected)

**Frontend (Vitest + Testing Library):**
- CV list page rendering
- CV editor form: add/remove experience entries, save
- Application panel CV section: link dropdown, duplicate button
- PDF generation (mock @react-pdf/renderer)
