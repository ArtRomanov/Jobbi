# Review Dimensions

Evaluate every section against these four dimensions. Not all will apply equally — use judgment.

## 1. Abstraction Level

The biggest failure mode in functional specs is mixing layers. Flag anything that belongs in a tech spec:

- Library or framework names (MarkItDown, openpyxl, pgvector)
- SQL, API paths, HTTP status codes, query parameters
- Config key names, environment variables, dependency lists
- Docker/infrastructure details
- Specific algorithms or thresholds presented as implementation decisions rather than constraints

**The test:** could a stakeholder unfamiliar with the codebase understand and validate this? If not, it's too technical.

**Exception:** some technical details are legitimate functional constraints — e.g., a 200-char file size limit or a 30-file cap per SOW. The difference is whether it describes a *user-facing constraint* or an *implementation choice*.

## 2. User Story Quality

User stories should anchor requirements to human outcomes. Flag:

- **"As a system"** — if the actor is the system itself, the format is being filled in mechanically. Reframe around the human who benefits.
- **Missing consequence** — "I want to X so that..." where "so that" is vague or absent. The consequence is what justifies the requirement.
- **Mechanical templates** — user stories that feel copy-pasted without real thought about user value.

## 3. User-Facing Feedback Completeness

A common blind spot: the spec defines system behavior precisely but never says what the user *sees*. Check for:

- What happens when something fails? (processing error, enrichment failure)
- What happens at edge cases? (file cap hit, dedup match, format not supported)
- Is the user informed, or does the system just act silently?

These are functional concerns, not technical ones — they belong in the spec.

## 4. Scope Placement

In Scope/Out-of-Scope sections, check that In-Scope lists functional capabilities, not implementation tasks. Items like "replace library X with library Y" or "revert docker-compose to postgres:17" are tech backlog items, not functional scope.

---

## What Good Looks Like

These patterns are worth calling out positively:

- **Concrete examples** that illustrate behavior without prescribing implementation (e.g., showing what a generated doc_name looks like vs. the raw filename)
- **Honest admissions** about over-engineering or past mistakes — rare and valuable in specs
- **Out-of-Scope lists** that pre-empt future scope creep by explicitly excluding adjacent features
- **Research or rationale** that justifies strategic decisions (not implementation choices)
- **Numbered consequences** — problems stated as cause -> symptom -> consequence

## Two-Doc Process

If the team follows a functional-spec-first, tech-spec-second process, apply this consistently:

- Don't present it as a choice — the process is already agreed
- Don't suggest "moving" detail as optional — frame it as a process issue
- Good pattern: suggest marking technical items with `[tech spec]` rather than deleting them, so the thinking isn't lost