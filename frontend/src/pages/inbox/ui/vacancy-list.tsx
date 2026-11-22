import { useCallback, useRef } from "react";
import { VacancyCard } from "@/entities/vacancy";
import type { Vacancy } from "@/entities/vacancy";
import { VacancyActions, useVacancyActions } from "@/features/vacancy-actions";
import { hasActiveFilters, type InboxFilterValues } from "@/features/inbox-filters";
import { Button, EmptyState, colors } from "@/shared/ui";
import {
  INBOX_EMPTY_DESCRIPTION,
  INBOX_EMPTY_TITLE,
  INBOX_NO_MATCHES_DESCRIPTION,
  INBOX_NO_MATCHES_TITLE,
  VACANCIES_LOAD_ERROR,
} from "../lib/constants";
import { pickFocusAfterRemove } from "../lib/helpers";
import { useVacancyList } from "../model/use-vacancy-list";

interface VacancyListProps {
  /** Changing it reloads the list (e.g. after a source finished scanning). */
  refreshKey: number;
  filters: InboxFilterValues;
  /** Called when a dismiss leaves no card to focus (the page focuses its heading). */
  onListEmptied: () => void;
}

/**
 * Inbox cards for the current filters, with "Load more" and card actions.
 * Owns the actions hook, so unmounting the list (leaving the Inbox) ends
 * any open Undo window. After a dismiss, focus moves to the Dismiss button of
 * the card that takes its place (or the one before), else to the page heading.
 */
export function VacancyList({ refreshKey, filters, onListEmptied }: VacancyListProps) {
  const {
    items,
    loadState,
    hasMore,
    isLoadingMore,
    loadMoreError,
    loadMore,
    retry,
    updateItem,
    removeItem,
    restoreItem,
  } = useVacancyList(refreshKey, filters);
  const { openSource, dismiss } = useVacancyActions({
    onUpdate: updateItem,
    onRemove: removeItem,
    onRestore: restoreItem,
  });
  const dismissButtonsRef = useRef(new Map<string, HTMLButtonElement>());

  const registerDismissButton = useCallback(
    (id: string, element: HTMLButtonElement | null): void => {
      if (element) dismissButtonsRef.current.set(id, element);
      else dismissButtonsRef.current.delete(id);
    },
    [],
  );

  const handleDismiss = useCallback(
    (vacancy: Vacancy): void => {
      const nextId = pickFocusAfterRemove(
        items.map((item) => item.id),
        vacancy.id,
      );
      dismiss(vacancy);
      const target = nextId === null ? undefined : dismissButtonsRef.current.get(nextId);
      if (target) target.focus();
      else onListEmptied();
    },
    [items, dismiss, onListEmptied],
  );

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
    return hasActiveFilters(filters) ? (
      <EmptyState title={INBOX_NO_MATCHES_TITLE} description={INBOX_NO_MATCHES_DESCRIPTION} />
    ) : (
      <EmptyState title={INBOX_EMPTY_TITLE} description={INBOX_EMPTY_DESCRIPTION} />
    );
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
            <VacancyCard
              vacancy={vacancy}
              actions={
                <VacancyActions
                  vacancy={vacancy}
                  onOpenSource={openSource}
                  onDismiss={handleDismiss}
                  onRegisterDismissButton={registerDismissButton}
                />
              }
            />
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
