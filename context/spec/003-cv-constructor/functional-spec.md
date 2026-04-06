# Functional Specification: CV Constructor

- **Roadmap Item:** CV Constructor (Phase 2 — CV Constructor & AI Assistant)
- **Status:** Completed
- **Author:** Poe (AI Product Analyst)

---

## 1. Overview and Rationale (The "Why")

Every job application deserves a tailored CV, but customizing from scratch is tedious and error-prone. The user needs a central place to build, manage, and tailor multiple CV versions — then link them to specific job applications.

**Problem:** The user currently manages CVs in external tools (Google Docs, Word) with no connection to their application pipeline. They lose track of which version was sent where, and duplicating+tailoring takes too long.

**Desired outcome:** A built-in CV builder with structured sections and free-text content, supporting multiple versions. The user can duplicate a CV directly from an application context, tailor it for the role, link it to the application, and export it as PDF.

**Success criteria:**
- The user can create a CV with all standard sections in under 5 minutes.
- Duplicating and tailoring a CV for a new role takes under 2 minutes.
- Every application can have a linked CV, visible in the detail panel.

---

## 2. Functional Requirements (The "What")

### 2.1 CV List Page

- **As a** user, **I want to** see all my CVs in one place, **so that** I can manage and organize my CV versions.
  - **Acceptance Criteria:**
    - [x] A "CVs" page is accessible from the main navigation bar.
    - [x] The page lists all CVs with: name, last updated date, and a count of linked applications.
    - [x] A "Create New CV" button is visible at the top of the page.
    - [x] Each CV row has actions: Edit, Duplicate, Download PDF, Delete.
    - [x] Deleting a CV shows a confirmation dialog: "Are you sure you want to delete this CV? Applications linked to it will be unlinked." On confirm, the CV is deleted.

### 2.2 CV Builder / Editor

- **As a** user, **I want to** create and edit a CV with structured sections, **so that** I can build a well-organized CV within Jobbi.
  - **Acceptance Criteria:**
    - [x] The CV editor is a dedicated page accessible from "Create New CV" or by editing an existing CV.
    - [x] The CV has a required name field (e.g., "Base CV", "Frontend CV") at the top.
    - [x] The CV has the following sections, each with a free-text content area:
      - **Personal Information** — Full name, email, phone, location, LinkedIn URL (structured fields)
      - **Professional Summary** — Free text
      - **Work Experience** — Multiple entries. Each entry: company, role, start date, end date (or "Present"), description (free text)
      - **Education** — Multiple entries. Each entry: institution, degree, field of study, start year, end year, description (free text)
      - **Skills** — Free text (e.g., comma-separated or bullet list)
      - **Languages** — Free text (e.g., "English — Fluent, German — B2")
    - [x] Work Experience and Education sections support adding and removing multiple entries via "Add" and "Remove" buttons.
    - [x] Changes are saved with a "Save" button. On success, show a toast: "CV saved."
    - [x] A "Back to CVs" link returns to the CV list page.

### 2.3 Duplicate and Tailor from Application

- **As a** user, **I want to** quickly duplicate a CV from within an application's detail panel, **so that** I can tailor it for that specific role without affecting my base CV.
  - **Acceptance Criteria:**
    - [x] The application detail side panel shows a "CV" section displaying the currently linked CV name (or "No CV linked").
    - [x] A "Link CV" dropdown allows selecting an existing CV to link to this application.
    - [x] A "Duplicate & Customize" button next to the dropdown creates an exact copy of the selected CV, names it "[Original Name] — [Company] [Role]", links it to this application, and opens the CV editor for customization.
    - [x] If no CV is selected, "Duplicate & Customize" is disabled.
    - [x] Unlinking a CV (selecting "None" in the dropdown) removes the link but does not delete the CV.

### 2.4 PDF Export

- **As a** user, **I want to** download my CV as a PDF, **so that** I can attach it to job applications outside of Jobbi.
  - **Acceptance Criteria:**
    - [x] A "Download PDF" button is available on the CV editor page and in the CV list row actions.
    - [x] Clicking it generates a formatted PDF containing all CV sections with their content.
    - [x] The PDF uses a clean, professional layout with section headings, proper spacing, and readable fonts.
    - [x] The PDF filename is the CV name (e.g., "Frontend_CV.pdf").

---

## 3. Scope and Boundaries

### In-Scope

- CV list page with CRUD operations (create, edit, duplicate, delete)
- CV builder with structured sections (Personal Info, Summary, Experience, Education, Skills, Languages)
- Multiple work experience and education entries per CV
- Link/unlink CVs to job applications from the detail panel
- Duplicate & Customize flow from application context
- Basic PDF export with clean formatting
- CV name as identifier

### Out-of-Scope

- **User Account Essentials** (completed — Phase 1)
- **Application Tracker** (completed — Phase 1)
- **Claude Chat Integration** (separate roadmap item — Phase 2)
- **Metrics Dashboard** (Phase 3)
- **Telegram/HeadHunter/LinkedIn integrations** (Phase 4)
- Rich text editing within sections (plain text for V1, rich text in future Phase 5)
- CV templates or themes
- Import CV from file (PDF, DOCX)
- AI-assisted CV writing (covered by Claude Chat Integration spec)
- Drag-and-drop section reordering
- Custom sections (user can only use the predefined set)
