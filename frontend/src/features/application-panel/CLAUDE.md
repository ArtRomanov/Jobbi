# Application Panel Feature

Side panel (drawer) that slides in from the right when a kanban card is clicked. Shows full application details with inline editing via React Hook Form, status history log, and delete with confirmation. Composed at the page level alongside KanbanBoard to avoid same-layer FSD imports.

- "Link CV" select uses `buildCvSelectChoices` (`entities/cv`): own CVs first (base first, labelled "(base)"), then tailored copies in a "Tailored copies" `<optgroup>` (spec 011 §2.5). Linking a CV by hand never makes it a tailored copy, and "Duplicate & Customize" creates an own CV.
