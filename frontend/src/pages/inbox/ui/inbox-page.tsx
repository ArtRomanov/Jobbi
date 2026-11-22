import { useCallback, useState } from "react";
import { SourcesPanel } from "@/features/manage-sources";
import { PageCard, PageHeader } from "@/shared/ui";
import { VacancyList } from "./vacancy-list";

/** Inbox: vacancies found in the user's sources, plus the Sources panel. */
export function InboxPage() {
  // Bumped when a source finishes scanning so the list shows the new cards
  const [refreshKey, setRefreshKey] = useState(0);
  const refreshList = useCallback(() => setRefreshKey((key) => key + 1), []);

  return (
    <PageCard maxWidth="720px">
      <PageHeader title="Inbox" subtitle="Vacancies Jobbi found in your sources" />
      <VacancyList refreshKey={refreshKey} />
      <SourcesPanel onScanFinished={refreshList} />
    </PageCard>
  );
}
