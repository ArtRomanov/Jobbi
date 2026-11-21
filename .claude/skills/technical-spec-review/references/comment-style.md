# Comment Style Guide

## Tone

Direct and objective. No filler phrases like "great job on", "this is a solid start", "consider possibly". Say what the problem is.

Avoid:
- Excessive hedging ("you might consider possibly...")
- Balanced praise that feels obligatory
- Long preambles before the actual feedback
- Speccing the fix in detail — point at problems and suggest direction, don't rewrite the spec for the author

## Format by Context

### Section-by-section review (the main format)

```
### [Section name]

**Issues** — direct, specific, no softening. If something is wrong or risky, say it plainly.
**Good** — only include this if there's something genuinely worth noting. Skip if there isn't.
```

Then an Overall Summary at the end:

```
## Overall Summary

**Findings by grade** — P0 / P1 / P2 / P3, each with its `**Why Pn** (rule id)` line (the `review-grading` skill)
**Patterns to fix** — recurring problems across multiple sections (name them once here, not repeated per section)
**What works** — brief, only what's actually solid
```

### Inline PR comment (auto-posted at diff line)
- 1-3 sentences, direct, actionable
- State the problem and suggest direction, no preamble — the line context is already visible

### General PR comment (full review)
- Section-by-section with Overall Summary
- Lead with the spec name in the title or first heading

### Inline doc comment (Google Docs, Notion)
- 2-4 sentences, direct, ends with a suggested action

### Async Slack
- Conversational, shorter, less formal

## Deduplication Rule

If the same problem appears in multiple sections, do **not** repeat it in each one. Mention it once in the Overall Summary under "Patterns to fix" and give one clear example from the spec.

The signal: if you're writing essentially the same critique for §2.3 that you already wrote for §2.1, stop. The repetition dilutes the review and makes it harder to act on.

This applies especially to systemic issues — wrong package layout, "unchanged reuse" claims, code samples in the spec — which tend to be authorial habits rather than one-off mistakes.

## Citing existing code

When referencing existing code, always be specific:
- **Good:** `BambooServiceImpl.kt:334`
- **Bad:** "there might be something similar in BambooService"

Vague references are not actionable and waste the author's time. If you can't name the file and line, either find them or omit the reference.

## Calling out wrong references

Tech specs frequently point at the wrong file or assume framework defaults that don't match project config. Each wrong reference is an individually citable finding worth its own bullet — don't bundle them.

**Bad (bundled):**
> Several references in the spec point at the wrong files; please verify each one.

**Good (specific):**
> Section 2.4: spec says hook goes in `BambooSyncJob`, but the actual termination transition happens in `BambooServiceImpl.kt:334/345`. The job is just a scheduled wrapper.

## Tech-spec-specific rule: no code samples

Tech specs must not contain application code samples. If you see a code block (function, class, method body), flag it — implementation belongs in the PR, not the spec.

The same goes for complete schema definitions (full column lists with types, DDL): the AWOS template asks for table names, key columns and relationships only.

When flagging a code sample, name the section and suggest converting to prose:
> §2.10 contains a Python block (`if old_status is None and new_status == "applied": …`). Tech specs shouldn't contain application code — convert to prose describing the condition.

## Overall Summary structure

Make the summary actionable, not a recap:

- **Findings by grade** — graded P0–P3 by the rules in the `review-grading` skill, numbered,
  terse, each followed by its `**Why Pn** (rule id): …` line. P0/P1 block; P2/P3 are the author's call. If there are no
  P0/P1 findings, say "No P0/P1."
- **Patterns to fix** — recurring habits, with one example each. These are the systemic issues the author should internalize, not just patch.
- **What works** — short bullets. Don't fabricate praise. If something is genuinely solid (e.g., a well-designed migration plan, a comprehensive risk table), name it. If nothing stands out, omit the section.
