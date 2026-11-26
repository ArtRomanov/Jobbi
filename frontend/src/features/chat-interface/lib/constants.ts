/**
 * Chat quick actions: each sends `template` as a normal chat message.
 * `requiresCv`: disabled until a CV is linked; `hiddenWithoutCv`: not shown at
 * all until then. The app has no UI language switch, so the texts are English.
 */
export const QUICK_ACTIONS = [
  {
    id: "refine-cv",
    label: "Refine my CV",
    requiresCv: true,
    hiddenWithoutCv: false,
    template:
      "Please review my CV and suggest specific improvements for the {role_title} role at {company_name}. Focus on wording, structure, and keyword optimization.",
  },
  {
    id: "cover-letter",
    label: "Write a cover letter",
    requiresCv: false,
    hiddenWithoutCv: false,
    template:
      "Please write a tailored cover letter for the {role_title} position at {company_name}, based on my CV and the job description.",
  },
  {
    id: "interview-prep",
    label: "Prep for interview",
    requiresCv: false,
    hiddenWithoutCv: false,
    template:
      "Please help me prepare for an interview for the {role_title} role at {company_name}. Suggest likely interview questions, key topics to research about the company, and preparation tips.",
  },
  {
    // Backlog #27: Markdown structure for the designed CV layout, same words
    id: "structure-cv",
    label: "Structure my CV",
    requiresCv: true,
    hiddenWithoutCv: true,
    template:
      "Structure my CV: add Markdown headings, sections and bullets without changing the wording.",
  },
] as const;

/** Toast after a CV change card is accepted (spec 011 §2.5). */
export const CARD_ACCEPTED_MESSAGE = "Change applied to your CV";
