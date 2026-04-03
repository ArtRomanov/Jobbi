/**
 * Kanban column definitions — ordered left-to-right on the board.
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
