"""Synthetic inputs for the CV chat eval: a fictional person and vacancy."""

CV = """# Alex Morgan
Senior Frontend Engineer
alex.morgan@example.com · +1 555 010 2030 · Lisbon, Portugal · github.com/alexmorgan-dev

## PROFILE

Frontend engineer with 8 years of experience building web apps for fintech and e-commerce. Focus on performance, design systems and developer experience.

## SKILLS

**Frontend:** TypeScript, JavaScript, Vue 3, React, Redux, HTML, CSS, Sass
**Tooling:** Vite, Webpack, Jest, Playwright, Storybook
**Other:** Node.js, REST, GraphQL, CI/CD, Figma

## EXPERIENCE

### Lead Frontend Engineer — Northwind Pay
Mar 2021 – Present

Payments platform, team of 12 engineers.

- **Rebuilt the checkout widget in Vue 3:** cut bundle size by 38% and raised conversion by 4%. **Scope:** 3 engineers, 40k daily users.
- **Introduced a shared design system:** reduced UI bugs by 30% across products. **Scope:** 5 product teams, 120 components.
- **Set up Playwright end-to-end tests:** caught 25 regressions before release in the first quarter. **Scope:** 2 web apps, CI on every PR.
- **Migrated the merchant dashboard to TypeScript:** removed a whole class of runtime errors. **Scope:** 180k lines, 6 months.

### Frontend Engineer — Bluefin Retail
Jun 2017 – Feb 2021

Online store for home goods, 2M monthly visitors.

- **Moved product pages to server-side rendering:** improved LCP from 4.1s to 1.9s. **Scope:** 15k product pages.
- **Built a reusable filter and search UI:** increased search usage by 22%. **Scope:** catalog of 60k items.
- **Automated visual regression checks with Storybook:** cut manual QA time by half. **Scope:** 200 stories.
- **Mentored junior developers:** two were promoted within a year. **Scope:** 4 mentees.

## CERTIFICATIONS

- AWS Certified Cloud Practitioner (2022)
- Google UX Design Certificate (2020)

## LANGUAGES

**English:** fluent (C1)
**Portuguese:** native
**Spanish:** intermediate (B1)
"""

VACANCY = """Senior Frontend Engineer (React) — Remote (EU)
Brightlane is a B2B SaaS for logistics analytics.
You will: build complex data-heavy dashboards in React + TypeScript, own our component library, improve performance of large tables and charts, work with Next.js, React Query, and Testing Library.
Must have: 5+ years frontend, strong React and TypeScript, performance optimisation, testing culture.
Nice to have: design systems, accessibility (WCAG), GraphQL.
"""

COMPANY = "Brightlane"
ROLE = "Senior Frontend Engineer"

PROFILE_TEXT = (
    "Frontend engineer with 8 years of experience building web apps for fintech "
    "and e-commerce. Focus on performance, design systems and developer experience."
)
