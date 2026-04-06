# Functional Specification: Claude Chat Integration

- **Roadmap Item:** Claude Chat Integration (Phase 2 — CV Constructor & AI Assistant)
- **Status:** Completed
- **Author:** Poe (AI Product Analyst)

---

## 1. Overview and Rationale (The "Why")

Job seekers spend significant time crafting CVs, writing cover letters, and preparing for interviews — often without feedback until it's too late. An AI assistant that knows the specific job context can provide instant, tailored guidance.

**Problem:** The user has no way to get real-time feedback on their application materials or prepare for interviews within their job search workflow. They'd need to open a separate AI tool and manually paste context.

**Desired outcome:** An AI chat assistant embedded in Jobbi, scoped to each job application. Claude has access to the application details (company, role, job URL) and linked CV, and can provide targeted help: refine CVs, generate cover letters, and prepare for interviews. Chat history is persisted so the user can revisit advice.

**Success criteria:**
- The user can start a conversation with Claude about a specific application in under 10 seconds (one click from the application panel).
- Quick-action buttons for CV refinement, cover letter generation, and interview prep produce useful results on the first try.
- The user can return to a previous conversation and see the full history.

---

## 2. Functional Requirements (The "What")

### 2.1 Application Chat Page

- **As a** user, **I want to** have a chat conversation with Claude about a specific job application, **so that** I can get tailored advice for my application materials and interview prep.
  - **Acceptance Criteria:**
    - [x] An "AI Assistant" button in the application detail side panel navigates to a dedicated chat page scoped to that application.
    - [x] The chat page shows the application context at the top: company name, role title, and linked CV name (if any).
    - [x] The chat interface has a message input area at the bottom and a scrollable message history area above.
    - [x] User messages appear on the right, Claude's responses on the left, with timestamps.
    - [x] Claude's responses stream in real-time (word by word) as they are generated.
    - [x] Chat history is persisted — refreshing the page or returning later shows the full conversation.
    - [x] The chat input supports multi-line text (Shift+Enter for new line, Enter to send).

### 2.2 Quick-Action Buttons

- **As a** user, **I want to** trigger common AI tasks with one click, **so that** I don't have to write prompts from scratch.
  - **Acceptance Criteria:**
    - [x] Three quick-action buttons are displayed above the chat input (or as a toolbar):
      - **"Refine my CV"** — Sends a prompt asking Claude to review the linked CV and suggest improvements for wording, structure, and keyword optimization for the specific role.
      - **"Write a cover letter"** — Sends a prompt asking Claude to generate a tailored cover letter based on the job role and the user's CV.
      - **"Prep for interview"** — Sends a prompt asking Claude to generate likely interview questions, company research tips, and preparation advice for the specific role and company.
    - [x] Each button is disabled if its prerequisite context is missing (e.g., "Refine my CV" is disabled if no CV is linked to the application).
    - [x] Clicking a button sends the pre-built prompt as a user message and Claude begins streaming a response.
    - [x] The user can continue the conversation after a quick action (e.g., ask follow-up questions about the cover letter).

### 2.3 Context Awareness

- **As a** user, **I want** Claude to know about my application and CV, **so that** its advice is specific to my situation, not generic.
  - **Acceptance Criteria:**
    - [x] Claude receives the application context as a system message: company name, role title, job URL, notes, and current status.
    - [x] If a CV is linked, Claude receives the full CV content (personal info, summary, work experience, education, skills, languages) in the system message.
    - [x] Claude does not reveal the system message content unless the user asks about it.
    - [x] If the user updates their CV or application details, the next message in the chat uses the updated context.

---

## 3. Scope and Boundaries

### In-Scope

- Application-scoped chat page accessible from the application panel
- Real-time streaming of Claude responses (SSE or WebSocket)
- Persisted chat history (messages stored in database per application)
- Three quick-action buttons: Refine CV, Write Cover Letter, Prep for Interview
- Context injection: application details + linked CV sent to Claude as system message
- Multi-line input with Enter to send, Shift+Enter for new line

### Out-of-Scope

- **User Account Essentials** (completed — Phase 1)
- **Application Tracker** (completed — Phase 1)
- **CV Constructor** (completed — Phase 2)
- **Metrics Dashboard** (Phase 3)
- **Telegram/HeadHunter/LinkedIn integrations** (Phase 4)
- Global/general-purpose chat (not tied to an application)
- Chat list page showing all conversations
- File attachments in chat
- Code execution or tool use by Claude
- Multiple AI models (Claude only)
- Chat export or sharing
- Token usage tracking or cost limits
