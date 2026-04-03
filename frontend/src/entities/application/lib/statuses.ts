/**
 * Application status definitions — domain knowledge about which statuses
 * exist and how they're labeled. Lives in `entities/application` because
 * it describes the application domain, not a specific user interaction.
 */
export const STATUSES = [
  { key: "researching", label: "Researching" },
  { key: "applied", label: "Applied" },
  { key: "interview", label: "Interview" },
  { key: "offer", label: "Offer" },
  { key: "rejected", label: "Rejected" },
  { key: "withdrawn", label: "Withdrawn" },
] as const;

export type StatusKey = (typeof STATUSES)[number]["key"];
