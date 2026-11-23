/** "Feb 20, 2026" for the row's "Updated …" line. */
export function formatCvDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/** "1 application" / "3 applications". */
export function formatLinkedCount(count: number): string {
  return `${count} application${count !== 1 ? "s" : ""}`;
}
