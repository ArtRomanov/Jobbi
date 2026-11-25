/** "Feb 20, 2026" for the row's "Updated …" line. */
export function formatCvDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export type CvRowAction = "edit" | "duplicate" | "pdf" | "html" | "delete";

/**
 * Unique accessible name of a row action, visible label first (WCAG 2.5.3),
 * e.g. "Edit My CV", "Export PDF: My CV".
 */
export function getCvActionLabel(action: CvRowAction, cvName: string): string {
  switch (action) {
    case "edit":
      return `Edit ${cvName}`;
    case "duplicate":
      return `Duplicate ${cvName}`;
    case "pdf":
      return `Export PDF: ${cvName}`;
    case "html":
      return `Download HTML: ${cvName}`;
    case "delete":
      return `Delete ${cvName}`;
  }
}

/** "1 application" / "3 applications". */
export function formatLinkedCount(count: number): string {
  return `${count} application${count !== 1 ? "s" : ""}`;
}
