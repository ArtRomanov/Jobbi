# Functional Specification: AI Chat Edits Application & CV via Tool Calls

- **Roadmap Item:** Follow-up enhancement to "AI Chat Integration" (Phase 2). Not a new roadmap item — this revises spec 004's "tool use by Claude" out-of-scope boundary, in the same way spec 007 revised the "Claude only" boundary.
- **Status:** Draft
- **Author:** Poe (AI Product Analyst)

---

## 1. Overview and Rationale (The "Why")

The AI assistant currently only produces text. When the user asks "tighten my summary" or "rewrite this bullet to emphasize impact", the assistant returns advice the user has to manually copy-paste back into the application or CV editor — a slow, error-prone step that defeats much of the assistant's value.

**Problem:** The chat sees the application and linked CV as context but cannot act on them. Every improvement requires the user to switch tabs and transcribe, often introducing typos, dropped lines, or formatting drift between the AI's suggestion and what ends up saved.

**Desired outcome:** The assistant can directly propose edits to the current application and its linked CV. Each proposal appears in the chat as a structured card showing exactly what would change (before/after diff). Nothing is saved until the user clicks **Accept** on the card; **Reject** discards the proposal. Multiple proposals in one assistant turn are reviewed independently. The assistant's text reply can sit alongside any number of these change cards.

**Success criteria:**

- A user who says "rewrite my summary to emphasize ML experience" gets back a text rationale plus an Accept/Reject card showing the new summary, and one click applies it.
- A user who says "tighten all my work bullets" gets one card per bullet that changes, and can keep the strong ones while rejecting awkward ones.
- After Accept, the linked CV (or application) reflects the change immediately and the next assistant message uses the updated context.
- No mutation ever lands without an explicit Accept click.

---

## 2. Functional Requirements (The "What")

### 2.1 Inline Change Cards in Chat

- **As a** user, **I want to** see exactly what the AI proposes to change before anything is saved, **so that** I never get a silent edit and can compare the suggestion to what's there now.
  - **Acceptance Criteria:**
    - [ ] When the assistant proposes a change, it renders in the conversation as a distinct **change card**, visually separated from regular assistant text bubbles.
    - [ ] Each card shows: the target (e.g., "Application status", "CV summary", "Work experience: Senior Engineer at Acme"), a **before** value, an **after** value, and two buttons: **Accept** and **Reject**.
    - [ ] For multi-line text (CV summary, bullet description), the diff is rendered with line-level visual differentiation (added vs. removed) so the user can scan it.
    - [ ] For structured edits (e.g., "add a new work experience entry"), the card shows the full proposed entry as the "after" with no "before" (since nothing existed) and clearly labels it as an addition.
    - [ ] Cards are interleaved naturally with the assistant's regular text reply — a single assistant turn can contain a paragraph of text plus N cards, in the order the assistant chose to present them.

### 2.2 Accept / Reject Lifecycle

- **As a** user, **I want** each proposed change to require my explicit approval, **so that** I retain full control over what lands in my application and CV.
  - **Acceptance Criteria:**
    - [ ] A new card starts in **Pending** state. Until Accept or Reject is clicked, no change is persisted to the application or CV.
    - [ ] Clicking **Accept** persists the change immediately and the card transitions to **Accepted** state — buttons are removed, the card shows a green check-style indicator, and the new value is visible in the application detail panel / CV editor on next view.
    - [ ] Clicking **Reject** transitions the card to **Rejected** state — buttons are removed, the card shows a strikethrough or muted styling, no DB write occurs to the underlying entity.
    - [ ] Card state is **persisted in chat history**. Refreshing the page or returning later shows each historical card in its final state (Accepted, Rejected, or Pending).
    - [ ] **Pending cards remain interactive after a refresh** — the user can come back later and click Accept or Reject on a card from a previous session, as long as the underlying entity still exists and the proposed value is still valid.
    - [ ] Each card decision is independent — accepting one card does not implicitly accept others in the same turn.
    - [ ] Cards cannot be re-decided. Once Accepted or Rejected, the buttons are gone. To revert an accepted change, the user asks the assistant to reverse it as a new card, or edits manually in the application/CV editor.

### 2.3 Conversation Continues With Updated Context

- **As a** user, **I want** the assistant to understand the latest state of my application and CV after I accept a change, **so that** follow-up suggestions don't contradict what was just applied.
  - **Acceptance Criteria:**
    - [ ] When the user sends the next message after accepting a card, the assistant's system context reflects the post-Accept state of the application and linked CV.
    - [ ] If the user accepts a CV summary rewrite and then asks "now make it shorter", the assistant works from the new summary, not the original.
    - [ ] Rejected cards do not affect future system context; they did not change anything.
    - [ ] The conversation history (text messages plus card decisions) is part of the context the assistant sees on subsequent turns, so the assistant knows what was previously proposed and decided.

### 2.4 Scope of Editable Targets

- **As a** user, **I want to** know exactly which fields the AI can touch, **so that** I can trust the assistant's reach and audit anything unexpected.
  - **Acceptance Criteria:**
    - [ ] On the chat page for `/applications/:id/chat`, the assistant can propose edits **only** to: (a) the application identified by `:id`, and (b) the CV currently linked to that application, if any.
    - [ ] The assistant **cannot** propose edits to other applications, other CVs the user owns, the user's profile, account settings, or anything outside the application/CV pair.
    - [ ] Editable application fields: `status`, `notes`, `role_title`, `company_name`, `job_url`. Status changes must use one of the valid stage values (Researching, Applied, Interview, Offer, Rejected, Withdrawn).
    - [ ] Editable CV fields: `summary`, `personal_info` (sub-fields), `skills`, `languages`, plus add/update/remove operations on `work_experience` entries and `education` entries.
    - [ ] If no CV is linked to the application, the assistant can still edit the application but cannot propose any CV changes; if asked, the assistant explains there's no CV linked and suggests linking one in the application panel.
    - [ ] The assistant cannot create new applications, new CV versions, or duplicate the linked CV. Those remain manual actions in the existing UI (deferred to a future spec).

### 2.5 Failure Surfacing on Apply

- **As a** user, **I want to** know clearly when an Accept click fails, **so that** I can retry or work around the problem.
  - **Acceptance Criteria:**
    - [ ] If the backend rejects an Accept (validation failure, conflict, network error, auth expired), the card stays in Pending state and an inline error message appears under it explaining the failure (e.g., "Couldn't apply: 'Hired' is not a valid status value").
    - [ ] The user can click Accept again to retry, or click Reject to dismiss.
    - [ ] If a card is for a target that no longer exists (e.g., the user manually deleted the linked CV in another tab), Accept fails with a clear message and the card is marked as Stale; Reject still works.
    - [ ] If the assistant's tool call is malformed (invalid field name, illegal value), the chat surfaces this as an inline assistant error message and no card is rendered.

---

## 3. Scope and Boundaries

### In-Scope

- The AI assistant on `/applications/:id/chat` can propose mutations to the current application and its linked CV via tool/function calls handled server-side under the user's auth.
- Inline change cards in the conversation with before/after rendering and Accept/Reject controls.
- Multiple change cards in a single assistant turn, each independently decidable.
- Persistence of card state (Pending / Accepted / Rejected / Stale) in chat history so cards survive reload.
- Updated assistant context after each Accept: subsequent turns see the new state.
- Editable fields: application (`status`, `notes`, `role_title`, `company_name`, `job_url`) and linked CV (`summary`, `personal_info`, `skills`, `languages`, plus add/update/remove on `work_experience` and `education` entries).
- Inline error surfacing when an Accept fails or a tool call is malformed.

### Out-of-Scope

- **Creating new entities** — no new applications, new CVs, or CV duplication via chat. Those remain manual UI actions and may be added in a future spec.
- **Cross-entity edits** — the chat for application A cannot edit application B, the user's profile, or any CV other than the one linked to A.
- **Auto-apply / silent edits** — every change requires an explicit Accept click. No "trust mode" or per-session auto-accept.
- **Re-deciding a settled card** — once Accepted or Rejected, a card is final. Reversing an Accepted change happens through a new chat turn or manual editing.
- **Undo of Accepted changes via the chat surface** — there is no Undo toast or "rewind to before this card." The application/CV history exists in the existing audit log; revert is a separate concern.
- **Multi-turn tool plans** — the assistant proposes changes in a single turn. Plans like "let me first read X, then I'll update Y" are not modeled here; tools are stateless one-shots.
- **Non-data tools** — no tools for fetching external URLs, scraping job postings, sending emails, or running code. Only the application/CV mutation tools described above.
- **Quality guarantees on the AI's suggestions** — output quality depends on the underlying LLM (Groq Llama 3.3 70B per spec 007). The user is the final arbiter via Accept/Reject.
- **Other roadmap items:** User Account Essentials, Application Tracker, CV Constructor, Metrics Dashboard, Telegram/HeadHunter/LinkedIn integrations.
