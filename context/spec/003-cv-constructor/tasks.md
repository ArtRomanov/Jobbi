# Tasks: CV Constructor

---

- [x] **Slice 1: CV CRUD API**
  - [x] Create `Cv` SQLAlchemy model with JSON columns. Create Alembic migration for `cvs` table. **[Agent: database-expert]**
  - [x] Create Pydantic schemas: `PersonalInfo`, `WorkExperienceEntry`, `EducationEntry`, `CvCreate`, `CvUpdate`, `CvRead`. **[Agent: python-backend]**
  - [x] Implement `cv_service.py`: list, create, get, update, delete, duplicate. **[Agent: python-backend]**
  - [x] Implement CV API routes: `GET /cvs`, `POST /cvs`, `GET /cvs/{id}`, `PATCH /cvs/{id}`, `DELETE /cvs/{id}`, `POST /cvs/{id}/duplicate`. Mount in v1 router. **[Agent: python-backend]**
  - [x] Verify: curl all endpoints — create CV (201), list (200), get (200), update (200), duplicate (201), delete (200). **[Agent: qa-tester]**

---

- [x] **Slice 2: Link CVs to applications**
  - [x] Add `cv_id` nullable FK column to `applications` table via Alembic migration. Add relationship to Application model. SET NULL on CV delete. **[Agent: database-expert]**
  - [x] Update Application schemas: add `cv_id` and `cv_name` to read schemas, `cv_id` to update schema. Update service to include CV name in responses. **[Agent: python-backend]**
  - [x] Verify: PATCH application with `cv_id` → links CV. GET application → shows `cv_id` and `cv_name`. Delete CV → application's `cv_id` becomes null. **[Agent: qa-tester]**

---

- [ ] **Slice 3: CV list page**
  - [ ] Regenerate OpenAPI types. Create `entities/cv/` slice with types from generated schema, API calls (list, create, get, update, delete, duplicate). **[Agent: typescript-frontend]**
  - [ ] Create `pages/cvs/` page: list all CVs with name, last updated, linked app count. Actions: Edit, Duplicate, Download PDF (disabled for now), Delete with confirmation. **[Agent: typescript-frontend]**
  - [ ] Add `/cvs` route (protected) to router. Add "CVs" link to navigation bar. **[Agent: typescript-frontend]**
  - [ ] Code review: Review CV entity and list page for FSD compliance and patterns. **[Agent: react-code-reviewer]**
  - [ ] Verify: Navigate to CVs page → see list. Create a CV via curl → appears in list. Duplicate → copy appears. Delete → removed. **[Agent: qa-tester]**

---

- [ ] **Slice 4: CV builder/editor page**
  - [ ] Create `features/cv-editor/` slice: `CvEditorForm` component with sections — name field, Personal Info (structured fields), Summary (textarea), Work Experience (dynamic add/remove entries), Education (dynamic add/remove), Skills (textarea), Languages (textarea). React Hook Form + Zod. **[Agent: typescript-frontend]**
  - [ ] Create `pages/cv-editor/` page: wraps CvEditorForm. On create mode → POST /cvs → redirect to /cvs. On edit mode → loads existing CV → PATCH /cvs/{id} on save. **[Agent: typescript-frontend]**
  - [ ] Add `/cvs/new` and `/cvs/:id/edit` routes (protected) to router. Wire "Create New CV" and "Edit" buttons from CV list page. **[Agent: typescript-frontend]**
  - [ ] Code review: Review dynamic form arrays, FSD segment separation, and component structure. **[Agent: react-code-reviewer]**
  - [ ] Verify: Create new CV → fill all sections including multiple experience entries → save → CV appears in list. Edit → modify → save → changes persisted. **[Agent: qa-tester]**

---

- [ ] **Slice 5: Application-CV linking UI**
  - [ ] Regenerate OpenAPI types to include updated application schemas with `cv_id`/`cv_name`. **[Agent: typescript-frontend]**
  - [ ] Add CV section to `features/application-panel/`: display linked CV name (or "No CV linked"), "Link CV" dropdown (fetches CV list), "Duplicate & Customize" button. **[Agent: typescript-frontend]**
  - [ ] Implement Duplicate & Customize: duplicates selected CV with name "[CV] — [Company] [Role]", links to application, navigates to CV editor. **[Agent: typescript-frontend]**
  - [ ] Code review: Review CV linking UX, dropdown patterns, and navigation flow. **[Agent: react-code-reviewer]**
  - [ ] Verify: Open application panel → link a CV → shows CV name. Duplicate & Customize → new CV created and linked → editor opens. Unlink → shows "No CV linked". **[Agent: qa-tester]**

---

- [ ] **Slice 6: PDF export**
  - [ ] Install `@react-pdf/renderer`. Create `features/cv-pdf/` slice: `CvDocument` component that renders CV data as a styled PDF document (section headings, proper spacing, professional fonts). **[Agent: typescript-frontend]**
  - [ ] Add `downloadCvPdf(cv)` utility that renders the CvDocument and triggers a browser download with filename "[CV name].pdf". **[Agent: typescript-frontend]**
  - [ ] Wire "Download PDF" button on CV list page (row action) and CV editor page. Lazy-load the PDF feature to avoid bundle bloat. **[Agent: typescript-frontend]**
  - [ ] Code review: Review PDF layout, lazy loading, and bundle impact. **[Agent: react-code-reviewer]**
  - [ ] Verify: Click Download PDF → PDF file downloaded with correct content and formatting. All CV sections present in the PDF. **[Agent: qa-tester]**

---

- [ ] **Slice 7: Backend test suite for CV constructor**
  - [ ] Integration tests for CV CRUD: create, list, get, update, delete, duplicate. **[Agent: python-backend]**
  - [ ] Tests for JSON column validation: valid/invalid work_experience and education structures. **[Agent: python-backend]**
  - [ ] Tests for application-CV linking: link, unlink, cv_name in response, SET NULL on CV delete. **[Agent: python-backend]**
  - [ ] Authorization tests: user can't access other user's CVs. **[Agent: python-backend]**
  - [ ] Verify: `pytest` runs all tests — 100% pass rate. **[Agent: qa-tester]**

---

- [ ] **Slice 8: Frontend test suite for CV constructor**
  - [ ] Add MSW handlers for all CV API endpoints. **[Agent: typescript-frontend]**
  - [ ] CV list page tests: renders CVs, duplicate, delete. **[Agent: typescript-frontend]**
  - [ ] CV editor tests: form rendering, add/remove experience entries, save. **[Agent: typescript-frontend]**
  - [ ] Application panel CV section tests: link dropdown, duplicate & customize button. **[Agent: typescript-frontend]**
  - [ ] Code review: Review test patterns and async handling. **[Agent: react-code-reviewer]**
  - [ ] Verify: `pnpm test` runs all tests — 100% pass rate. **[Agent: qa-tester]**
