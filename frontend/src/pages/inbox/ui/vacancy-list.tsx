import { VacancyCard } from "@/entities/vacancy";
import { Button, EmptyState, colors } from "@/shared/ui";
import {
  INBOX_EMPTY_DESCRIPTION,
  INBOX_EMPTY_TITLE,
  VACANCIES_LOAD_ERROR,
} from "../lib/constants";
import { useVacancyList } from "../model/use-vacancy-list";

interface VacancyListProps {
  /** Changing it reloads the list (e.g. after a source finished scanning). */
  refreshKey: number;
}

/** Inbox cards, newest first, with "Load more"; empty state when there are none. */
export function VacancyList({ refreshKey }: VacancyListProps) {
  const { items, loadState, hasMore, isLoadingMore, loadMoreError, loadMore, retry } =
    useVacancyList(refreshKey);

  if (loadState === "loading") {
    return (
      <p role="status" style={{ fontSize: "0.875rem", color: colors.textMuted }}>
        Loading vacancies…
      </p>
    );
  }

  if (loadState === "error") {
    return (
      <div>
        <p role="alert" style={{ fontSize: "0.875rem", color: colors.error, marginBottom: "0.5rem" }}>
          {VACANCIES_LOAD_ERROR}
        </p>
        <Button type="button" variant="secondary" onClick={retry}>
          Try again
        </Button>
      </div>
    );
  }

  if (items.length === 0) {
    return <EmptyState title={INBOX_EMPTY_TITLE} description={INBOX_EMPTY_DESCRIPTION} />;
  }

  return (
    <div>
      <ul
        aria-label="Vacancies"
        style={{
          listStyle: "none",
          margin: 0,
          padding: 0,
          display: "flex",
          flexDirection: "column",
          gap: "0.75rem",
        }}
      >
        {items.map((vacancy) => (
          <li key={vacancy.id}>
            <VacancyCard vacancy={vacancy} />
          </li>
        ))}
      </ul>
      {hasMore ? (
        <div style={{ marginTop: "1rem", textAlign: "center" }}>
          <Button
            type="button"
            variant="secondary"
            loading={isLoadingMore}
            onClick={() => void loadMore()}
          >
            Load more
          </Button>
          {loadMoreError ? (
            <p role="alert" style={{ marginTop: "0.5rem", fontSize: "0.75rem", color: colors.error }}>
              {loadMoreError}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
