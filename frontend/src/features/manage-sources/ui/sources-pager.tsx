import { Button } from "@/shared/ui";
import { SOURCES_PAGER_LABEL } from "../lib/constants";

interface SourcesPagerProps {
  /** Current page, 0-based. */
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
}

/**
 * Previous / page numbers / Next under the source list; nothing for a single
 * page. Focus stays on the pressed control: Previous / Next are
 * `keepFocusable` (aria-disabled at the ends), so reaching an end does not
 * drop focus to <body>.
 */
export function SourcesPager({ page, pageCount, onPageChange }: SourcesPagerProps) {
  if (pageCount <= 1) return null;
  const isFirst = page === 0;
  const isLast = page === pageCount - 1;

  return (
    <nav aria-label={SOURCES_PAGER_LABEL} style={{ marginTop: "0.75rem" }}>
      <ul style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem", listStyle: "none", margin: 0, padding: 0 }}>
        <li>
          <Button
            type="button"
            variant="secondary"
            keepFocusable
            disabled={isFirst}
            onClick={() => onPageChange(page - 1)}
          >
            Previous
          </Button>
        </li>
        {Array.from({ length: pageCount }, (_, index) => {
          const isCurrent = index === page;
          return (
            <li key={index}>
              <Button
                type="button"
                variant={isCurrent ? "primary" : "secondary"}
                aria-label={`Page ${index + 1}`}
                aria-current={isCurrent ? "page" : undefined}
                onClick={() => onPageChange(index)}
              >
                {index + 1}
              </Button>
            </li>
          );
        })}
        <li>
          <Button
            type="button"
            variant="secondary"
            keepFocusable
            disabled={isLast}
            onClick={() => onPageChange(page + 1)}
          >
            Next
          </Button>
        </li>
      </ul>
    </nav>
  );
}
