# Review Dimensions

Evaluate every section against these four dimensions. Not all will apply equally — use judgment.

## 1. Logic consistency

Does the technical approach hold together internally? Flag:

- **Contradictions between sections** — e.g., one section says the flow is stateless, another relies on session state
- **One shape described two ways** — for every shape the spec defines, compare every statement about it (shape table, schema section, prompt or agent-guide section); e.g. a table that allows "any other key" on a row while the schema section asks for one strict row schema that rejects them
- **A default that switches off silently** — for every implicit default the change adds (an automatic column, label or fallback), the spec must name the condition that turns it off and tell every author of that condition (the agent guide included) what to add instead
- **A moved predicate left behind** — a filter or liveness predicate (an `archived` guard, a status filter) moved to a new source must list every place the old one is enforced (queries, validators, agent recipes, docs) with its new form
- **A staged rollout with no "before"** — for every flag, dry run or manual switch the rollout relies on, the spec must state what each changed read returns before the switch flips; a read moved to backfilled data while the backfill still runs dry is a finding
- **Writers and readers the spec did not list** — a change to a lock order, transaction boundary or the meaning of a stored value must name every writer and reader of the rows or value (scheduled jobs, admin actions such as a retry, external services, cached clients) and what each sees, not only the paths the spec was written around
- **A precedent reused "like X" without its guards** — when the spec says a new value, role or path behaves "like X" (pushed like the pursuit lead, merged like the owner), open X and list every guard it has (a seat check, an alias or alias-only check, a pending-change keep, a never-emptied rule); each guard the spec neither carries over nor rules out is a finding — e.g. new deal roles that copied the pursuit lead's seat rule but not its alias-only guard, so a holder whose HubSpot user sits under a second address was cleared in HubSpot on every update
- **A new value checked against the old one** — a new value written into an existing column (a timestamp that can now lie in the future, a new enum member, a new outcome) or a new result of a shared function must list every reader and writer that filters, compares or branches on it and what each does with the new value; a writers-and-readers row marked "unchanged" must name the predicate it was checked against
- **A new resolution outcome missed by a reverse caller** — a new outcome or lookup added to a shared resolution (a funnel's result, an owner/employee mapping, a matching rule) must list every caller in both directions, found by grepping the name and its inverse, and what each does with the new outcome
- **A mechanism with no named invariant** — an ordering-dependent bean (controller advice, filter, event listener, scheduled job) with no explicit order, or a derived state a rule reads (a value that was clamped, overridden, defaulted or moved) reconstructed from a coincidence of values instead of written by a named producer into a named column or field
- **A read that rests on client state** — Jobbi's frontend fetches with useEffect/useState and refreshes via `refreshKey`; for every list or counter the spec changes, list where it renders and what triggers its refetch after a write elsewhere (another page, the worker, the bot); a stale view with no refresh path is a finding
- **Two states told apart by a proxy** — when the spec tells two states apart by a value that stands in for them (a count, a flag, a length) and not by the state itself, it must name the case where both states give the same value and what the code does in it — e.g. a loaded page count as the test for a list kept in the cache against a reloaded one, when a list left with one page reloads with the same count
- **Incomplete flows** — happy path defined, error paths missing or hand-waved
- **Assumptions stated but never validated** — "we assume X" with no follow-up addressing what happens if X is false
- **Dangling data** — data appears in one place but is never produced or consumed correctly elsewhere
- **Consumers off the main path** — for every value the spec makes optional (nullable, possibly empty) and every setting, placeholder or key it adds, grep the name and list each consumer: build-time tasks (code generation, migration runs, scanners), background jobs, and readers a guard is said to protect. One the spec does not say what it gets is a finding, and so is a test that fills the value in by hand as the proof that a consumer receives it — e.g. a Flyway placeholder added for the running app but not for the build's codegen migration run, or a "the guard makes it unreachable" null check on a value a later step can still leave empty
- **What the framework does between the caller and the code** — for every request parameter, cached or startup-read value, and preview/write pair the spec adds or changes, the spec must state its runtime handling and name the edge value a test uses: how a list query parameter binds, when a setting is read (once at startup vs per request) and how tests override it, and the one predicate a preview and its write both read
- **"Unchanged reuse" claims that aren't actually unchanged** — describing existing code as extended-but-unchanged when the change is real

The test: read each section in isolation, then read it in context. If isolated reading creates a different mental model than contextual reading, the spec has internal inconsistency.

## 2. Alignment with functional spec

Does the tech spec actually implement what the functional spec describes? Flag:

- **Missing requirements** — functional ACs that have no corresponding technical answer
- **Scope creep** — the tech spec adds capability the functional spec doesn't ask for (over-eager engineering)
- **Misinterpretations** — the technical solution solves a different problem than the functional spec describes
- **Direct AC violations** — a technical decision that explicitly contradicts a functional AC (e.g., "no delay window" vs a 30-second cache)

If no functional spec is provided: skip this dimension and note at the top of the review.

## 3. Implementation quality

Does the proposed approach fit the project? Flag:

- **Pattern violations** — abstractions that don't match existing conventions in the codebase (wrong package, wrong base class, wrong layering)
- **Over-engineering** — unnecessary abstraction layers, premature generalization, invented complexity the problem doesn't justify
- **Under-engineering** — shortcuts that will obviously break, missing error handling, ignored edge cases
- **Reinventing existing components** — if you can see it in the codebase, name the existing class/function/pattern that should be reused or extended instead
- **New dependencies introduced implicitly** — Thymeleaf, Caffeine, etc. added without being called out as new deps
- **Code samples in the spec** — application-level code blocks belong in the PR, not the spec. The data model is described as the AWOS template asks — table names, key columns and relationships — not as a complete schema definition (full column lists with types, DDL); flag those too.

> **For language- or framework-specific concerns** (FastAPI, SQLAlchemy async, Alembic, python-telegram-bot, React/FSD), consult the relevant domain expert agent or skill before making a call. Don't flag something as a pattern violation based on general knowledge if a project-specific expert can give a more grounded answer.

## 4. Existing solutions and reference points

Actively look for opportunities to point to what already exists:

- **Name existing components by file and line** — vague "there might be something similar" is not useful. `BambooServiceImpl.kt:334` is.
- **Cite the right reference pattern** — if the spec proposes a new auth mechanism, point at `security/api/ApiConfigurer.kt` as the existing pattern for service-to-service auth in the project
- **Verify referenced components actually exist** — tech specs frequently point at the wrong file, assume framework defaults that don't match project config, or invent classes. Each wrong reference is an individually citable finding.
- **Check for reusable utilities** — if a library or utility already in the project handles part of this, say so

---

## What good looks like

Worth calling out positively when present:

- **Clear failure paths** described alongside happy paths
- **Explicit references to existing components** that will be reused or extended (not invented)
- **A data model** (tables, key columns, relationships) that maps cleanly to the functional spec
- **Scope decisions that explicitly rule out adjacent complexity** — "we deliberately don't do X because Y"
- **Migration plans** with specific filename conventions matching project style
- **Risk tables** that name real risks and concrete mitigations (not generic "we'll handle errors carefully")
- **Test plans** that cover both unit and integration layers and use the project's existing test harness

## Cross-repo / cross-system specs

If a tech spec describes work across multiple repos or services:

- **Mark boundaries explicitly** — readers of one repo's PR shouldn't be asked to approve files that won't land there
- **Either split into per-repo specs** or keep one spec with clearly labeled informational sections for cross-repo work
- **Flag rollout coordination risks** — shipping one side without the other usually breaks the feature

This is especially relevant when one of the systems lives in a separate repo from the PR being reviewed.
