---
name: frontend-code-quality
description: "Enforces frontend code quality rules: one component per file, DRY patterns, shared layout components, and consistent error handling. Use when writing, reviewing, or refactoring React/TypeScript code in the Jobbi frontend."
---

# Frontend Code Quality Rules

These rules apply to all React/TypeScript code in the Jobbi frontend (`frontend/src/`).

## Rule 1: One Component Per File

Each `.tsx` file must define and export **only one React component** (a function returning JSX).

- A second function that returns JSX is a **violation** — extract it to its own file.
- Helper functions, constants, validators, and types must NOT live in UI component files — see Rule 5.

**Bad:**
```tsx
// settings-page.tsx
export function SettingsPage() { return <div>...</div>; }
function ChangePasswordSection() { return <form>...</form>; } // VIOLATION
```

**Good:**
```tsx
// settings-page.tsx
import { ChangePasswordSection } from "./change-password-section";
export function SettingsPage() { return <div>...<ChangePasswordSection /></div>; }

// change-password-section.tsx
export function ChangePasswordSection() { return <form>...</form>; }
```

## Rule 2: DRY Shared Styles

Inline style objects repeated across **3 or more files** must be extracted to reusable components in `shared/ui/`.

Available shared components (use these instead of inline styles):
- `<AuthLayout maxWidth?>` — Full-screen centered layout for unauthenticated pages
- `<PageCard maxWidth?>` — Centered card wrapper for authenticated pages
- `<PageHeader title subtitle />` — H1 heading + subtitle paragraph
- `<Divider label? />` — Horizontal rule separator
- `<FormSelect label options error? ...register />` — Styled select with label
- `<FormTextarea label error? ...register />` — Styled textarea with label

## Rule 3: DRY Error Handling

Form submission error handling must use the shared `handleApiError` utility from `@/shared/api`:

```typescript
import { handleApiError } from "@/shared/api";

// In catch block:
} catch (error: unknown) {
  handleApiError(error, showToast, {
    409: "An account with this email already exists.",
    401: "Invalid email or password.",
  });
}
```

Do NOT copy-paste the `isApiError` check pattern across files.

## Rule 4: FSD Segment Separation in UI Files

UI component files (`ui/*.tsx`) must contain **only the React component and its JSX**. Everything else belongs in the appropriate FSD segment:

- **Helper/transform functions** (e.g., `userToFormValues`, `formatPayload`) → `lib/` segment (e.g., `lib/helpers.ts`)
- **Constants and config objects** (e.g., `REMOTE_OPTIONS`, `APPLICATION_STATUSES`) → `lib/` segment (e.g., `lib/constants.ts`)
- **Zod schemas and validators** (e.g., `settingsSchema`, `loginSchema`) → `model/` segment (e.g., `model/schemas.ts`)
- **Types and interfaces** → `model/` segment (e.g., `model/types.ts`)

**Bad:**
```tsx
// pages/settings/ui/settings-page.tsx
const REMOTE_OPTIONS = [...];                    // VIOLATION — constant in UI file
const settingsSchema = z.object({...});          // VIOLATION — schema in UI file
function userToFormValues(user: User) {...}       // VIOLATION — helper in UI file
export function SettingsPage() { return <div>...</div>; }
```

**Good:**
```
pages/settings/
├── lib/
│   └── constants.ts        # REMOTE_OPTIONS
│   └── helpers.ts          # userToFormValues
├── model/
│   └── schemas.ts          # settingsSchema
├── ui/
│   └── settings-page.tsx   # Only the component
└── index.ts
```

This rule applies to all FSD layers: `pages/`, `features/`, `entities/`.

## Rule 5: DRY Layout Wrappers

Pages must use the shared layout components instead of inline wrapper divs:
- Auth pages (login, register, forgot-password, reset-password) → `<AuthLayout>`
- Authenticated pages with card content (settings, new-application) → `<PageCard>`
- All page titles → `<PageHeader>`
- Section dividers → `<Divider>`