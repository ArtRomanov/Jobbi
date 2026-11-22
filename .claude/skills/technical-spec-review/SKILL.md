---
name: technical-spec-review
description: Review technical specifications for logic consistency, alignment with functional spec, implementation quality, and project pattern compliance. Use this skill whenever the user shares a tech spec and asks for feedback, a review, thoughts, or comments — even if phrased casually like "take a look at this", "what do you think", or "review this spec". Also triggers on "review the tech spec in PR 123", "review techspec in PR", "post comments on the tech spec", "check this tech spec", or "fix my tech spec". Applies to tech specs, design docs, and implementation proposals for software features. Especially useful when the team follows a two-doc process (functional spec first, tech spec second).
---

# Tech Spec Review

Review technical specifications section by section, identifying issues across logic, alignment with functional spec, implementation quality, and codebase fit. Grounded in one principle: a tech spec describes **how** something will be built and must hold together internally, match the functional spec's intent, and fit the existing codebase.

## Reference Files

| File | Contents |
|------|----------|
| `references/review-dimensions.md` | Detailed review criteria for all four dimensions |
| `references/comment-style.md` | Comment tone, format by context, deduplication rules |

## Invocation

```
/technical-spec-review                  # Manual review mode — user shares spec text
/technical-spec-review path/to/spec.md  # Self-review mode — review local file and apply fixes
/technical-spec-review 123              # PR review mode — auto-post comments on PR #123
/technical-spec-review 123 path/to/technical-spec.md   # PR mode with explicit file path
/techspec-review                        # Legacy alias — still supported
```

## Review Dimensions

Apply these four dimensions to every section (see `references/review-dimensions.md` for full details):

1. **Logic consistency** — flag contradictions, missing error paths, unvalidated assumptions, dangling data, one shape described two ways, a default that switches off silently, a moved predicate left behind, a staged rollout with no "before", writers and readers the spec did not list, a new value checked against the old one, a new resolution outcome missed by a reverse caller, a mechanism with no named invariant (`references/review-dimensions.md` §1)
   — and missed pairs: for each response field or flag, stored JSON key, placeholder syntax or display rule the spec changes, grep its readers and writers across `backend/app` (API, services, discovery worker, bot), `backend/tests`, `frontend/src` and the generated `frontend/src/shared/api/schema.d.ts` consumers; one the spec says nothing about is a finding
   — and consumers off the main path: for each value the spec makes optional and each setting, placeholder or key it adds, every consumer (build-time tasks, background jobs, readers behind a guard) and what it gets
2. **Alignment with functional spec** — flag missing requirements, scope creep, misinterpretations
3. **Implementation quality** — flag pattern violations, over-engineering, under-engineering, reinventions
4. **Existing solutions and reference points** — actively name files/classes/methods that should be reused


> **For language- or framework-specific concerns** (e.g. FastAPI, SQLAlchemy async, Alembic, python-telegram-bot, React/FSD), consult the relevant domain expert agent or skill before making a call — e.g. `python-backend`, `database-expert`, `typescript-frontend`, `fsd-reviewer`, or the `fastapi-best-practices` / `react-feature-sliced-design` skills. Don't flag something as a pattern violation based on general knowledge if a project-specific expert can give a more grounded answer.

---

## Mode 1: Manual Review

When the user shares spec text directly or points to a file without asking to post to a PR.

1. Review each section against the four dimensions
2. Present findings as a section-by-section review (see `references/comment-style.md`)
3. End with an Overall Summary covering graded findings (P0–P3), patterns to fix, and what works
4. If the user asks for a comment, draft it matching their context (PR, Google Docs, Slack)

---

## Mode 2: Self-Review (Local File)

When the user points to a local spec file (no PR number). This mode reviews the file in place and offers to fix issues directly.

### Step 1: Read the spec file

Read the file the user pointed to. If no file was given, search for tech spec files in the working directory:
```bash
# Common patterns
**/technical-spec.md
**/tech-spec.md
**/technical-considerations.md
context/spec/*/technical-spec.md
context/spec/*/technical-considerations.md
```
If multiple found, ask the user which one. Also look for a sibling `functional-spec.md` to use as the alignment reference.

### Step 2: Read the functional spec (if present)

If a sibling functional spec exists, read it before reviewing — alignment checks need both documents. If not, note at the top of the review that alignment was skipped.

### Step 3: Scan the codebase for referenced components

For every file, class, method, or table the spec mentions, verify it exists. Note discrepancies — pointing at the wrong file is a common tech spec failure mode and worth flagging individually.

### Step 4: Review against all four dimensions

Review the full spec content section by section. For each finding, record:
- **Line number** in the file
- **Dimension** (Logic, Alignment, Quality, Existing)
- **Issue** — what's wrong
- **Suggestion** — direction to fix it (don't write the fix in detail)

### Step 5: Present findings with line references

Show findings grouped by grade — P0–P3 per the `review-grading` skill, each with its `**Why Pn** (rule id)` line — with clickable `file_path:line_number` references:

```
## Issues found in context/spec/034-feature/technical-spec.md

**P1:**
1. `technical-spec.md:88` **[Logic]** — Session-based flow contradicts STATELESS config in SecurityConfiguration.kt:46.
   **Why P1** (P1-a bug): built as written, every request after login fails authentication.
2. `technical-spec.md:120` **[Alignment]** — Functional spec AC 2.6 says "no delay window"; 30-second cache violates this.
   **Why P1** (P1-b unmet criterion): AC 2.6 "no delay window" — the cache delays changes by up to 30 s.

**P2:**
3. `technical-spec.md:45` **[Quality]** — Wrong package: services proposed under service/oauth/ but project has security/oauth/.
   **Why P2** (P2-b convention): package layout convention; no functional effect.
4. `technical-spec.md:200` **[Quality]** — Code sample in spec body. Tech specs must not contain code samples.
   **Why P2** (P2-b convention): `references/comment-style.md` "no code samples" rule.

**Existing solutions:**
- Line 76: BambooSyncJob is the wrong hook point — actual transition is in BambooServiceImpl.kt:334

Fix issues 1-4? [All / Pick / Skip]
```

### Step 6: Apply fixes

For each accepted fix, edit the file directly using the Edit tool:
- Rewrite contradictions with consistent language
- Replace wrong file references with verified ones
- Remove code samples and complete schema definitions (keep table names, key columns and relationships)
- Add explicit "out of scope / cross-repo" markers where boundaries are blurred

**Do not** restructure or reformat unchanged sections. Only touch lines with findings.

### Step 7: Summary

After edits, show:
- Number of issues fixed (with before/after for each)
- Number of issues skipped
- Any remaining items the user should address manually (e.g., decisions that need stakeholder input)

---

## Mode 3: PR Auto-Post Review

When the user references a PR number. This mode reads the spec from the PR diff and posts comments directly.

### Step 1: Get PR metadata and diff

```bash
# Get PR diff
gh pr diff PR_NUMBER

# Get PR metadata
gh pr view PR_NUMBER --json baseRefOid,headRefOid,title,files
```

### Step 2: Identify tech spec file(s)

Find files matching patterns like `**/technical-spec.md`, `**/tech-spec.md`, `**/technical-considerations.md` in the diff. If the user provided an explicit path, use that. If multiple spec files exist, ask which to review. Also locate the sibling `functional-spec.md` for alignment checks (it may not be in the diff but should still be read).

### Step 3: Verify codebase references

For every file, class, method, or table the spec names, scan the actual codebase to confirm it exists at the claimed location. Tech specs frequently point at the wrong file or assume defaults that don't match project config — these are individually citable findings.

### Step 4: Review and classify findings

Review the spec content against the four dimensions. Grade every finding P0–P3 per the `review-grading` skill with a `**Why Pn** (rule id)` line. Group findings by section, then write an Overall Summary with the findings by grade (P0–P3), recurring patterns, and what works.

### Step 5: Present findings to user for approval

Before posting, show the user the full review. Use `AskUserQuestion` to confirm. If the user says "edit", let them modify findings before posting.

### Step 6: Post general comment

Post the review as a single PR comment:

```bash
gh pr comment PR_NUMBER --body "REVIEW_TEXT"
```

Format the comment as a section-by-section review followed by an Overall Summary (see `references/comment-style.md` for the exact format).

### Step 7: Report results

Show the user:
- Number of findings posted
- Link to the PR

