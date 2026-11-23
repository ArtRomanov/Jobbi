# Functional Specification: Base CV, File Upload and Text CV Editor

- **Roadmap Item:** Follow-up to "CV Constructor" (Phase 2) — not a new roadmap item. Fixes backlog #7 (tailored copies chain) and delivers backlog #8 (base CV) and #3 (free-text editing; PDF had only the heading). Revises spec 003 (form editor) and spec 008 (AI edits to CV fields).
- **Status:** Approved
- **Author:** Poe (AI Product Analyst)

---

## 1. Overview and Rationale (The "Why")

The user already has a CV — usually a PDF or Word file — and wants Jobbi to tailor it for each vacancy. Today they have to retype it into a form with separate fields (personal info, summary, each job, each degree, skills, languages). The form is slow to fill and limiting to edit, and an exported PDF can come out with only the heading.

"Add & tailor CV" (spec 009) makes things worse: it copies the most recently updated CV, which is usually the copy made for the previous application. Copies chain ("Base CV — Codery … — Welldin …"), and the AI chat for one company works from a CV tailored for another.

**Desired outcome:** the user uploads their CV once or writes it as free text, marks it as their **base CV**, and every "Add & tailor CV" starts from that base. CVs are edited as one formatted text with a live preview, the AI chat proposes edits to that text, and copies made for applications are kept apart from the user's own CVs.

**Success criteria:**
- A user with a PDF or DOCX CV gets an editable Jobbi CV from it in one upload, without retyping.
- "Add & tailor CV" always starts from the base CV; a copy is never made from another application's copy unless the user picks it on purpose.
- Every CV can be edited freely as text, and its exported PDF contains the whole CV, including Russian and other non-Latin text.
- The AI chat can still propose CV edits that the user accepts or rejects one by one, and an accepted edit is never silently lost.

**Terms used below:**
- **Base CV** — the one CV the user marks as the starting point for tailoring. At most one per user.
- **Own CV** — any CV that is not a tailored copy (the base CV is also an own CV).
- **Tailored copy** — a CV that "Add & tailor CV" created for an application.
- **Formatting** — simple text markup the preview and the PDF show formatted: `# Heading`, `## Section`, `### Subsection`, `**bold**`, `*italic*`, `- list item`, `1. numbered item`, and links written as `[text](https://…)` or as a bare web or email address. Only web (`http`, `https`) and email links are clickable; any other link is shown as plain text. Any other markup (tables, HTML tags, images) is shown exactly as typed.
- **Change card** (designed in spec 008, built for the first time by this spec, for CV text only) — a block in the application chat in which the assistant proposes one edit, showing "before" and "after" with Accept and Reject buttons. Nothing changes until the user clicks Accept. Each card is decided on its own, its state (Pending, Accepted, Rejected, Stale) is kept in the chat history, Pending cards stay clickable after a reload, and a decided card cannot be decided again.

---

## 2. Functional Requirements (The "What")

### 2.1 Writing and editing a CV as text

- **As a** user, **I want to** edit my CV as one free text with simple formatting, **so that** I can shape it the way I want without a rigid form.
  - **Acceptance Criteria:**
    - [ ] The CV editor has a name field and one text area for the whole CV, next to a live preview showing the text formatted (see **Formatting**). On narrow screens (phone width) the editor and the preview are two tabs, "Edit" and "Preview", and "Edit" is open first.
    - [ ] The preview updates as the user types. A short formatting hint ("# Heading · ## Section · **bold** · - list · [link](https://…)") is shown near the text area.
    - [ ] The editor header shows a "Base" label when the CV is the base CV, and the application it was made for when it is a tailored copy (see 2.5).
    - [ ] "Create New CV" opens the editor with an empty text area and the placeholder "Write your CV here, or upload a PDF/DOCX on the CVs page."
    - [ ] The CV text can be up to 20 000 characters, counting every character including spaces and line breaks. Typing stops at the limit, pasted text is cut to it, and a counter "N / 20 000" is shown once more than 18 000 characters are used.
    - [ ] The name is required, up to 255 characters; input stops at 255. A name that is empty or only spaces shows "Required" and blocks saving. Several CVs may have the same name.
    - [ ] "Save" is active only when the name or the text differs from the saved version. After saving, the toast "CV saved" is shown. If saving fails, "Could not save the CV. Please try again." is shown and the user's changes stay in the editor.
    - [ ] If the CV was changed elsewhere after the editor opened it (for example, a change card was accepted in the AI chat, or the CV was saved in another tab), "Save" does not overwrite it and shows "This CV was changed elsewhere (for example in the AI chat). Reload to see the latest version." The user's unsaved text stays in the editor so they can copy it.
    - [ ] Leaving the editor with unsaved changes — by moving to another page of Jobbi, closing the tab or reloading — asks "You have unsaved changes. Leave without saving?" with "Leave" and "Stay" (closing or reloading uses the browser's own leave prompt).
    - [ ] The old form editor (separate fields for personal info, summary, work experience, education, skills and languages, used when creating and editing a CV) no longer exists anywhere in Jobbi.

### 2.2 Existing CVs move to text

- **As a** user with CVs made in the form, **I want** them converted to text automatically, **so that** I lose nothing.
  - **Acceptance Criteria:**
    - [ ] Every existing CV is converted once into formatted text, leaving out empty parts, in this shape:

      ```
      # Jane Doe
      jane@example.com · +374 99 123456 · Yerevan · https://linkedin.com/in/jane

      ## Summary
      Frontend developer with 6 years of experience…

      ## Experience
      ### Senior Frontend Developer — Acme
      Jan 2022 – Present
      Built the design system…

      ## Education
      ### BSc Computer Science — Yerevan State University
      2014 – 2018

      ## Skills
      React, TypeScript, Next.js

      ## Languages
      English (C1), Russian (native)
      ```

    - [ ] If the full name in the form was empty, the top heading is the CV name. Fields of the personal info other than the name are joined on one line with " · ".
    - [ ] After the conversion, every value the user had entered in the form (full name, email, phone, location, links, summary, each job's role, company, dates and description, each degree's degree, institution, dates and description, skills, languages) appears in the CV text. CV names, links to applications and dates stay as they were.
    - [ ] A CV whose form was completely empty becomes a CV with empty text.
    - [ ] No user gets a base CV from the conversion; every user starts with no base CV until they mark one (or upload a CV, see 2.3).

### 2.3 Uploading a CV file

- **As a** user, **I want to** upload my existing CV as a PDF or DOCX, **so that** I don't retype it.
  - **Acceptance Criteria:**
    - [ ] The CVs page has an "Upload CV" button next to "Create New CV". It accepts one `.pdf` or `.docx` file at a time, up to 5 MB. While the file is processed, the button shows "Uploading…" and cannot be clicked again.
    - [ ] Jobbi extracts the file's text in reading order (for multi-column layouts, column by column) and creates a new own CV named after the file without the extension, cut to 255 characters ("Uploaded CV" if nothing is left). The text is used as is: Jobbi does not reword, reorder or reformat it, and does not add markup. Original fonts, columns and images are not kept. Characters in the text that look like markup (for example a line starting with "- ") are shown formatted, like any typed text.
    - [ ] After the upload, the editor of the new CV opens with the notice "Text extracted from your file. Check the line breaks and save." The CV already exists at that point; leaving without changes keeps it.
    - [ ] If the user has no base CV, the uploaded CV becomes the base CV and the notice adds "This CV is now your base CV." If they already have one, the base does not change.
    - [ ] The file type is judged by its content, not only by its name. A file that is not a real PDF or DOCX shows "Upload a PDF or DOCX file." A file over 5 MB shows "The file is larger than 5 MB." A file with no readable text (a scan, an image-only PDF, a password-protected file) shows "Could not read text from this file. Upload a PDF with selectable text or a DOCX." Any other failure shows "Could not upload this file. Please try again." In every error case no CV is created.
    - [ ] Text longer than 20 000 characters is cut to 20 000, and the notice adds "The text was longer than 20 000 characters and was cut."
    - [ ] The uploaded file itself is not stored; only the extracted text is kept.

### 2.4 Base CV

- **As a** user, **I want to** mark one CV as my base, **so that** tailoring always starts from the right version.
  - **Acceptance Criteria:**
    - [ ] Each CV on the CVs page that is not the base has a "Make base" action. Using it makes that CV the base, shows the toast "Base CV updated", and the previous base (if any) becomes an ordinary own CV. At most one CV per user is the base at any time.
    - [ ] The base CV is shown first on the CVs page with a "Base" label.
    - [ ] When the user has no base CV, the CVs page shows "Mark one of your CVs as base — "Add & tailor CV" will start from it." above "My CVs" (only when the user has at least one CV).
    - [ ] A tailored copy can also be made the base. It then becomes an own CV for good: it leaves "Tailored for applications", does not return there when another CV later becomes the base, and stays linked to its application.
    - [ ] Deleting the base CV leaves the user with no base CV until they mark another one. Jobbi never picks a new base by itself (except on upload, see 2.3).
    - [ ] Each user's base CV is their own; one user's choice never affects another user.

### 2.5 CVs page: own CVs and tailored copies

- **As a** user, **I want** copies made for applications kept apart from my own CVs, **so that** my list stays clear and I never tailor from the wrong copy by accident.
  - **Acceptance Criteria:**
    - [ ] The CVs page has two sections. "My CVs" lists the base CV first, then the other own CVs, most recently updated first. "Tailored for applications" lists tailored copies, most recently updated first. A section with nothing in it is not shown, except "My CVs", which shows "No CVs yet. Upload your CV or create one." when the user has no CVs at all.
    - [ ] Each tailored copy shows the application it was made for as "<Company> — <Role>". Clicking it opens the dashboard with that application's panel open. If that application was deleted, it shows "Application deleted" instead of the link.
    - [ ] Copies made by "Add & tailor CV" before this change (for example the ones made for Kleos, Codery and Welldin) appear under "Tailored for applications". CVs the user linked to an application by hand (by choosing a CV in the application panel) stay in "My CVs"; linking a CV by hand never makes it a tailored copy.
    - [ ] Open, duplicate, export to PDF and delete are available for own CVs and tailored copies alike. A duplicate is named "<name> (copy)" and is always an own CV.
    - [ ] Deleting a CV first asks for confirmation, as today ("Are you sure you want to delete "<name>"? Applications linked to it will be unlinked. This action cannot be undone."). If the CV was linked to an application, the application stays and simply has no CV linked.

### 2.6 "Add & tailor CV" starts from the base CV

- **As a** user, **I want** "Add & tailor CV" to copy my base CV, **so that** the AI chat tailors the right CV.
  - **Acceptance Criteria:**
    - [ ] In the "Add to tracker" dialog (opened from a card in the Inbox), the CV choice is preselected with the user's base CV.
    - [ ] If the user has no base CV, nothing is preselected and "Add & tailor CV" stays disabled until a CV is chosen; under the choice the hint "Choose a CV to tailor, or mark one as base on the CVs page." is shown. "Add to tracker" without a CV still works.
    - [ ] The choice lists own CVs first (the base first, labelled "(base)"), then tailored copies in a separate group named "Tailored copies".
    - [ ] The new copy is named "<chosen CV name> — <Company> <Role>" (an empty company or role is left out; cut to 255 characters), is linked to the new application and appears under "Tailored for applications". After that the AI chat of the new application opens with the unsent message prepared, as in spec 009.

### 2.7 AI chat edits the CV text

- **As a** user, **I want** the AI chat to propose concrete edits to my CV text, **so that** I keep the accept/reject control I have today.
  - **Acceptance Criteria:**
    - [ ] In the application chat, the assistant works from the full current text of the CV linked to the application (and still from the application itself): asked about any part of the CV, it can quote it.
    - [ ] A proposed CV edit appears as a change card titled "CV text" that shows the passage as it is now ("before") and the proposed passage ("after"), with removed lines and added lines marked in different colours, plus Accept and Reject. An addition shows only "after", labelled with where it goes ("Added at the start", "Added after: <first words of the preceding line>" or "Added at the end"). A removal shows only "before", labelled "Removed".
    - [ ] Accept saves the CV at once (an editor open on the same CV then gets the "changed elsewhere" message on its next save, see 2.1): it replaces exactly that passage (or inserts or removes it) and changes nothing else. Reject changes nothing.
    - [ ] Accept fails, the card stays Pending with an error under it, and the CV does not change, when:
      - the passage is no longer in the CV (the user or another accepted card changed it): "This part of the CV has changed since the suggestion. Ask the assistant again." — and the card is marked Stale (Reject still works);
      - the passage appears more than once in the CV: "This text appears more than once in the CV. Ask the assistant to quote a longer part.";
      - the result would be longer than 20 000 characters: "This change would make the CV longer than 20 000 characters."
    - [ ] One assistant reply can contain several CV cards, and each is accepted or rejected on its own. Cards still Pending when a new reply arrives stay clickable. The next reply works from the CV text after all accepted cards.
    - [ ] If no CV is linked to the application, the assistant proposes no CV cards and, when asked, says that no CV is linked and suggests linking one in the application panel.
    - [ ] The assistant proposes no edits to the application itself (status, notes, role, company, job link); those cards stay in spec 008 for later. Asked to change the application, it explains what to change and where.

### 2.8 Export to PDF

- **As a** user, **I want** the exported PDF to contain my whole CV, **so that** I can send it to employers.
  - **Acceptance Criteria:**
    - [ ] "Export PDF" produces a file named "<CV name>.pdf" (characters not allowed in file names are replaced with "_") that contains the whole CV text, formatted like the preview (headings, bold, italic, lists, clickable web and email links), on A4 pages with page breaks as needed. The CV name itself is not printed; the document starts with the CV text.
    - [ ] Russian and other non-Latin text (for example Armenian) appears correctly in the PDF, in the preview and in the editor.
    - [ ] The PDF of a CV with empty text has only the CV name as its title.

---

## 3. Scope and Boundaries

### In-Scope

- Free-text CV editor with simple formatting, live preview, character limit, protection against losing unsaved or concurrent changes; removal of the form editor.
- One-time conversion of every existing CV from form fields to text.
- Upload of one PDF/DOCX (up to 5 MB) at a time into a new CV, text used as is.
- One base CV per user: "Make base", the base on upload when none exists, no automatic base otherwise (including after the conversion).
- CVs page split into "My CVs" and "Tailored for applications", including copies made before this change; delete with confirmation.
- "Add & tailor CV" preselecting the base CV, or nothing when there is none.
- AI chat change cards for CV text passages, built for the first time here (spec 008's CV field edits are replaced by text edits).
- PDF export of the whole formatted text, including non-Latin text.

### Out-of-Scope

- AI tidying or rewording of uploaded text; OCR of scanned files; keeping the original file, its layout or images; uploading several files at once.
- A visual (WYSIWYG) editor, PDF design themes or templates, and CV languages or translations.
- More than one base CV, or a base per role or language.
- The AI chat creating or duplicating CVs (still manual, as in spec 008), and change cards for application fields (left to spec 008).
- Other backlog items (batch adding sources, digest posts, AI limit notices, chat streaming display, collapsible Inbox sections, undo on source removal) and spec 010 (aggregator site parsers).
- Other roadmap items: HeadHunter Integration, LinkedIn Integration.
