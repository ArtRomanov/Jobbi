# Comment Style Guide

## Tone

Keep the tone direct without being harsh. Acknowledge what works before flagging what doesn't — but don't be formulaic about it. If something is mostly fine, say so and move on. If something is a fundamental problem, say that clearly.

Avoid:
- Excessive hedging ("you might consider possibly...")
- Balanced praise that feels obligatory
- Long preambles before the actual feedback

## Format by Context

### Inline MR/PR comment (auto-posted at diff line)
- 1-3 sentences, direct, actionable
- State the problem and suggest a fix
- No preamble — the line context is already visible

### General MR comment (cross-cutting findings)
- Numbered list of findings
- Lead with "Functional spec review" header
- Group related issues together

### Inline doc comment (Google Docs, Notion)
- 2-4 sentences, direct, ends with a suggested action

### Async Slack
- Conversational, shorter, less formal

## Deduplication Rule

If the same issue appears in multiple sections, don't echo it each time — raise it once as a general comment at the document level. Repeating the same comment four times dilutes it and makes the review harder to act on.

The signal: if you're writing essentially the same comment for section 2.2 that you already wrote for 2.1, stop. Instead, flag it as a document-level pattern: "This runs through 2.1-2.4 — suggest a single pass rather than fixing section by section."

This applies especially to abstraction level issues, which tend to be a habit of the author rather than a one-off mistake.

## Overall Impression (Summary Comment)

When reviewing the full spec, structure the summary as:

**Problems** — short bullets, direct language, no softening
**Good** — short bullets, same directness

Be objective. If the spec has a structural problem that runs through every section, name it once clearly rather than repeating it section by section.