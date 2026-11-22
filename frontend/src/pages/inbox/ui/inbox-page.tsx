import { useCallback, useId, useRef, useState } from "react";
import { SourcesPanel } from "@/features/manage-sources";
import { DEFAULT_INBOX_FILTERS, InboxFilters } from "@/features/inbox-filters";
import type { InboxFilterValues } from "@/features/inbox-filters";
import type { RemovedVacancySource, VacancySource } from "@/entities/vacancy-source";
import { PageCard, PageHeader, VISUALLY_HIDDEN_STYLE } from "@/shared/ui";
import { VacancyList } from "./vacancy-list";

/** Inbox: filterable vacancies found in the user's sources, plus the Sources panel. */
export function InboxPage() {
  // Bumped when a source finishes scanning so the list shows the new cards
  const [refreshKey, setRefreshKey] = useState(0);
  const refreshList = useCallback(() => setRefreshKey((key) => key + 1), []);
  const vacanciesHeadingId = useId();
  const titleRef = useRef<HTMLHeadingElement>(null);
  const focusTitle = useCallback(() => titleRef.current?.focus(), []);
  const [filters, setFilters] = useState<InboxFilterValues>(DEFAULT_INBOX_FILTERS);
  // Mirrored from the Sources panel, so the filter needs no request of its own
  const [sources, setSources] = useState<readonly VacancySource[]>([]);
  const [removedSources, setRemovedSources] = useState<readonly RemovedVacancySource[]>([]);
  const handleSourcesChange = useCallback(
    (nextSources: readonly VacancySource[], nextRemoved: readonly RemovedVacancySource[]) => {
      setSources(nextSources);
      setRemovedSources(nextRemoved);
    },
    [],
  );

  return (
    <PageCard maxWidth="720px">
      <PageHeader title="Inbox" subtitle="Vacancies Jobbi found in your sources" titleRef={titleRef} />
      {/* h1 > h2 "Vacancies" (screen readers only) > card h3s; "Sources" is the other h2 */}
      <section aria-labelledby={vacanciesHeadingId}>
        <h2 id={vacanciesHeadingId} style={VISUALLY_HIDDEN_STYLE}>
          Vacancies
        </h2>
        <InboxFilters
          value={filters}
          onChange={setFilters}
          sources={sources}
          removedSources={removedSources}
        />
        <VacancyList refreshKey={refreshKey} filters={filters} onListEmptied={focusTitle} />
      </section>
      <SourcesPanel onScanFinished={refreshList} onSourcesChange={handleSourcesChange} />
    </PageCard>
  );
}
