---
name: functional-spec-review
description: Review functional specifications for quality, abstraction level, and process compliance. Use this skill whenever the user shares a spec section and asks for thoughts, feedback, a comment, or a review — even if they use casual phrasing like "what do you think about this", "help me write a comment", or "review this". Also triggers on "review the spec in MR 123", "review funcspec in MR", "post comments on the spec", "review my spec", "check this spec before I push", or "fix my functional spec". Applies to functional specs, business specs, product specs, and requirements documents. Especially useful when the team follows a two-doc process (functional spec first, tech spec second).
---

# Functional Spec Review

Review functional specifications section by section, identifying issues and drafting comments. Grounded in one principle: a functional spec describes **what the system does for the user** and **why**, not how it's built.

## Reference Files

| File | Contents |
|------|----------|
| `references/review-dimensions.md` | Detailed review criteria for all four dimensions |
| `references/comment-style.md` | Comment tone, format by context, deduplication rules |

## Invocation

```
/funcspec-review                  # Manual review mode — user shares spec text
/funcspec-review path/to/spec.md  # Self-review mode — review local file and apply fixes
/funcspec-review 123              # PR review mode — auto-post comments on PR #123
/funcspec-review 123 path/to/functional-spec.md   # PR mode with explicit file path
```

## Review Dimensions

Apply these four dimensions to every section (see `references/review-dimensions.md` for full details):

1. **Abstraction level** — flag tech-spec content: SQL, API paths, library names, implementation decisions
2. **User story quality** — flag "As a system", missing consequences, mechanical templates
3. **User-facing feedback** — flag missing error states, edge case UX, silent system behavior
4. **Scope placement** — flag implementation tasks in In-Scope lists


---

## Mode 1: Manual Review

When the user shares spec text directly or points to a file without asking to post to an MR.

1. Review each section against the four dimensions
2. Present findings grouped by grade (P0–P3 per the `review-grading` skill, each with its
   `**Why Pn** (rule id)` line), then **Good** (tone: `references/comment-style.md`)
3. If the user asks for a comment, draft it matching their context (MR, Google Docs, Slack)

---

## Mode 2: Self-Review (Local File)

When the user points to a local spec file (no MR number). This mode reviews the file in place and offers to fix issues directly.

### Step 1: Read the spec file

Read the file the user pointed to. If no file was given, search for functional spec files in the working directory:
```bash
# Common patterns
**/functional-spec.md
**/func-spec.md
context/spec/*/functional-spec.md
```
If multiple found, ask the user which one.

### Step 2: Review against all four dimensions

Review the full spec content section by section. For each finding, record:
- **Line number** in the file
- **Dimension** (Abstraction, User Story, User Feedback, Scope)
- **Issue** — what's wrong
- **Suggestion** — how to fix it

### Step 3: Present findings with line references

Show findings grouped by grade — P0–P3 per the `review-grading` skill, each with its `**Why Pn** (rule id)` line — with clickable `file_path:line_number` references:

```
## Issues found in context/spec/033-feature/functional-spec.md

**P1:**
1. `functional-spec.md:45` **[User Feedback]** — No mention of what user sees when approval is blocked.
   **Why P1** (P1-b unmet criterion): the blocked-approval outcome has no stated behaviour, so no acceptance criterion can cover it.

**P2:**
2. `functional-spec.md:72` **[Abstraction]** — SQL implementation detail. Rewrite as: "duplicate files are detected and not re-processed."
   **Why P2** (P2-b convention): `functional-spec-review` abstraction rule — tech-spec content in a functional spec; no user-visible effect.
3. `functional-spec.md:130` **[Scope]** — In-Scope item names a system, not a capability.
   **Why P2** (P2-b convention): scope-placement rule; the capability is still implied.

**Good:**
- Line 68: tier table is concrete and stakeholder-readable
- Line 93: explicit no-rejection decision prevents scope creep

Fix issues 1-3? [All / Pick / Skip]
```

### Step 4: Apply fixes

For each accepted fix, edit the file directly using the Edit tool:
- Rewrite abstraction violations to functional language
- Add missing user-facing feedback as new bullets or ACs
- Rephrase scope items as capabilities
- Mark tech-spec items with `[tech spec]` tag if the team uses two-doc process

**Do not** restructure or reformat unchanged sections. Only touch lines with findings.

### Step 5: Summary

After edits, show:
- Number of issues fixed (with before/after for each)
- Number of issues skipped
- Any remaining items the user should address manually (e.g., missing content that needs domain knowledge)

---

## Mode 3: MR Auto-Post Review

When the user references a PR number. This mode reads the spec from the PR diff and posts comments directly.

### Step 1: Get PR metadata and diff

```bash
# Get PR diff
gh pr diff PR_NUMBER

# Get PR metadata (base/head SHAs for inline comments)
gh pr view PR_NUMBER --json baseRefOid,headRefOid
```

### Step 2: Identify functional spec file(s)

Find files matching patterns like `**/functional-spec.md`, `**/func-spec.md`, `**/spec.md` in the diff. If the user provided an explicit path, use that. If multiple spec files exist, ask the user which to review. Use `gh pr diff PR_NUMBER` to identify changed files.

### Step 3: Review and classify findings

Review the spec content against the four dimensions. Grade every finding P0–P3 per the `review-grading` skill with a `**Why Pn** (rule id)` line, and group them by grade; keep a short **Good** list.

### Step 4: Present findings to user for approval

Before posting, show the user what will be posted:

```
## General comment (will be posted as MR note):

**Functional spec review**

**P1**
1. **[User Feedback]** Section 2.1: No mention of what user sees when approval is blocked...
   **Why P1** (P1-b unmet criterion): ...

**P2**
2. **[Abstraction]** Section 2.2: Named individuals — define by role, not by person...
   **Why P2** (P2-b convention): ...

**Good** — {bullets}

Post this comment? [Yes / Edit / Cancel]
```

Use `AskUserQuestion` to confirm. If the user says "edit", let them modify findings before posting.

### Step 5: Post general comment

Post all findings as a single general PR comment:

```bash
gh pr comment PR_NUMBER --body "COMMENT_TEXT"
```

Format the comment as:
```markdown
**Functional spec review**

### P0 / ### P1 / ### P2 / ### P3   (only the grades that have findings)
{numbered findings, each prefixed with dimension tag and followed by its `**Why Pn** (rule id): …` line}

---
**Good** — {bullets}
```

### Step 6: Report results

Show the user:
- Number of findings posted
- Link to the PR


