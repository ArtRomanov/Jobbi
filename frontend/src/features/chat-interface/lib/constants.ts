export const QUICK_ACTIONS = [
  {
    id: "refine-cv",
    label: "Refine my CV",
    requiresCv: true,
    template:
      "Please review my CV and suggest specific improvements for the {role_title} role at {company_name}. Focus on wording, structure, and keyword optimization.",
  },
  {
    id: "cover-letter",
    label: "Write a cover letter",
    requiresCv: false,
    template:
      "Please write a tailored cover letter for the {role_title} position at {company_name}, based on my CV and the job description.",
  },
  {
    id: "interview-prep",
    label: "Prep for interview",
    requiresCv: false,
    template:
      "Please help me prepare for an interview for the {role_title} role at {company_name}. Suggest likely interview questions, key topics to research about the company, and preparation tips.",
  },
] as const;
