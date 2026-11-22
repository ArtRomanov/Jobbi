---
name: review-grading
description: The P0–P3 grade scale for review findings — what each grade means as numbered rules (P0-a … P3-a), how to reach a grade, and the Why-line format. Load it whenever you grade a review finding — local review (/pr-review and its reviewer agents), CodeRabbit comments (/resolve-pr-comments), spec reviews, the flows' triage — so every grader uses one scale.
user-invocable: false
---

# Review grading — P0 to P3

**The single source of the grade scale.** `reviewer-backend` and `reviewer-frontend` preload this skill (`skills:`);
`/pr-review`, `/resolve-pr-comments`, `/functional-spec-review`, `/technical-spec-review` and the flows load it before
grading. Change the scale here only — nothing else carries a copy.

Every finding gets one grade and one line above its fix:
`**Why Pn** ({rule id}): {source — quoted criterion, quoted rule + file, or failure scenario} — {consequence if it ships, who is affected, loud or silent, does a revert undo it}`.
P0/P1 block the merge and carry `**Owner**` and `**Escape**` lines; P2/P3 never block — the user decides keep or drop.

| Grade | Meaning | Examples | Action |
|---|---|---|---|
| **P0 — Blocker** | Security hole, data loss/corruption, silently wrong money or workload data, a migration that damages data or can't be reversed, or an existing production flow broken | wrong totals in user-facing metrics; missing access-control check; changelog trigger dropping rows | Must fix before merge |
| **P1 — Major** | Real bug or breaking change; acceptance criterion unmet or implemented wrong; mandated project rule broken with real consequence | behaviour backwards; filter contradicting its entries; API change without contract updated | Must fix before merge |
| **P2 — Minor** | Code quality/convention, no functional or user-visible effect | duplicated helper; unclear naming; missing i18n key in a dev-only string | User decides; never blocks |
| **P3 — Nit** | Style/preference | wording, ordering | User decides; never blocks |

### What each grade means — the rules a finding must meet

Each grade is defined by numbered rules. A finding takes the **highest grade whose rule it meets with a cited source**,
and its Why line names that rule: `**Why P1** (P1-b unmet criterion): AC 2.3 says … — the code keeps …`.

**P0 — Blocker.** The change does harm that a user didn't opt into and that a normal fix-forward may not undo. Meets P0 if any:
- **P0-a security** — an access check missing or bypassable, a credential exposed in code or logs, data visible to a role that must not see it.
- **P0-b data** — rows lost, overwritten or corrupted; a migration that damages data or cannot be reversed.
- **P0-c silent money/workload** — a revenue, cost, margin, FTE, utilization or workload figure that is wrong but looks
  plausible (no error, no empty state), so people act on it.
- **P0-d production flow** — an existing flow that works today in production stops working (crash, 500, blocked action).

**P1 — Major.** The change is wrong, but the harm is visible, contained or revertible. Meets P1 if any:
- **P1-a bug** — a concrete input produces wrong behaviour or an error, in code the diff adds or changes.
- **P1-b unmet criterion** — a quoted acceptance criterion or stated behaviour of the spec is unmet or implemented backwards.
- **P1-c breaking change** — an API, contract or shared component changes in a way an existing caller breaks on, or an
  API change ships without the contract updated.
- **P1-d mandated rule** — a rule written in `CLAUDE.md`, `.claude/rules/` or a skill is broken *and* breaking it has a
  real consequence (a CI failure, a raw i18n key shown to users, a security control weakened).

**P2 — Minor.** Worth fixing, but nothing a user or the system would notice. Meets P2 if any:
- **P2-a quality** — duplication, an unneeded abstraction, dead code, unclear naming, a missing test for a non-critical path.
- **P2-b convention** — a project convention broken with no functional or user-visible effect.
- **P2-c unsourced** — anything that would be P0/P1 but has no cited source or could not be verified. Only for that:
  a spec gap or convention checked against the code is P2-b or P1-b, not P2-c.

**P3 — Nit.** Preference only. **P3-a** wording, ordering, formatting, "I'd have written it differently".

### How to reach the grade

1. Reason first, in this order: (1) the concrete consequence if it ships, (2) who or what is affected, (3) does it fail
   loudly or silently, (4) does a revert undo it (a Flyway migration or corrupted data does not).
2. Walk the rules top-down: P0-a … P0-d, then P1-a … P1-d, then P2, then P3. Stop at the first rule the finding meets
   **with a source**. No source → P2-c at most.
3. Torn between two grades means unsure whether a rule is met: grade by the highest rule you are sure is met and say
   what is uncertain. Rarity of the trigger, a loud failure, or the cost of one extra fix round never lower a met rule —
   state them in the Why line instead.
4. A met rule is lowered only by step 5 (style cap) or when a P1-d breach has no real consequence; name both:
   `**Why P2** (P1-d met, no consequence): …`.
5. Style, naming, preference and code organization are never above P2.
6. Silence is valid. No findings → say so; never manufacture findings to justify the review.

Boundaries in one line each: **P0 vs P1** — does it harm data, money, security or production for users who didn't opt
in? **P1 vs P2** — is a requirement unmet, or a written rule broken with real consequence? **P2 vs P3** — would anyone
other than the reviewer care?
