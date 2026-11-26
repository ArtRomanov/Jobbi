import { useCallback, useId, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { SourcesPanel } from "@/features/manage-sources";
import { InboxFilters } from "@/features/inbox-filters";
import type { InboxFilterValues } from "@/features/inbox-filters";
import type { RemovedVacancySource, VacancySource } from "@/entities/vacancy-source";
import { useCollapsibleSection } from "@/shared/lib";
import { PageCard, PageHeader, SectionHeader, SectionToggle } from "@/shared/ui";
import { LIST_COLLAPSED_STORAGE_KEY } from "../lib/constants";
import { getSourceParam, initialFilters } from "../lib/helpers";
import { VacancyList } from "./vacancy-list";

/** Inbox: filterable vacancies found in the user's sources, plus the Sources panel. */
export function InboxPage() {
  // Bumped when a source finishes scanning (new cards) or is edited (new name on cards)
  const [refreshKey, setRefreshKey] = useState(0);
  const refreshList = useCallback(() => setRefreshKey((key) => key + 1), []);
  const vacanciesHeadingId = useId();
  const titleRef = useRef<HTMLHeadingElement>(null);
  const focusTitle = useCallback(() => titleRef.current?.focus(), []);
  // `?source=<key>` is read once: later filter changes do not touch the URL
  const [searchParams] = useSearchParams();
  const [filters, setFilters] = useState<InboxFilterValues>(() => initialFilters(searchParams));
  // A `?source=` link opens a collapsed list for this visit only (the saved choice stays)
  const listSection = useCollapsibleSection(LIST_COLLAPSED_STORAGE_KEY, {
    forceExpanded: getSourceParam(searchParams) !== null,
  });
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
      {/* h1 > h2 "Vacancies" > card h3s; "Sources" is the other h2 */}
      <section aria-labelledby={vacanciesHeadingId}>
        <SectionHeader
          id={vacanciesHeadingId}
          title="Vacancies"
          hasDivider={false}
          action={
            <SectionToggle
              label="Vacancies"
              isExpanded={listSection.isExpanded}
              controlsId={listSection.regionId}
              onToggle={listSection.toggle}
            />
          }
        />
        {/* `hidden`, not unmount: filters, loaded pages and Undo survive a collapse */}
        <div id={listSection.regionId} hidden={!listSection.isExpanded}>
          <InboxFilters
            value={filters}
            onChange={setFilters}
            sources={sources}
            removedSources={removedSources}
          />
          <VacancyList refreshKey={refreshKey} filters={filters} onListEmptied={focusTitle} />
        </div>
      </section>
      <SourcesPanel
        onScanFinished={refreshList}
        onSourcesChange={handleSourcesChange}
        onSourceEdited={refreshList}
      />
    </PageCard>
  );
}
