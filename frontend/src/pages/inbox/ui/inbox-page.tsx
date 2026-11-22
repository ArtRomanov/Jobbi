import { SourcesPanel } from "@/features/manage-sources";
import { EmptyState, PageCard, PageHeader } from "@/shared/ui";
import { INBOX_EMPTY_DESCRIPTION, INBOX_EMPTY_TITLE } from "../lib/constants";

/** Inbox: vacancies found in the user's sources, plus the Sources panel. */
export function InboxPage() {
  return (
    <PageCard maxWidth="720px">
      <PageHeader title="Inbox" subtitle="Vacancies Jobbi found in your sources" />
      {/* The vacancy list replaces this placeholder in a later slice */}
      <EmptyState title={INBOX_EMPTY_TITLE} description={INBOX_EMPTY_DESCRIPTION} />
      <SourcesPanel />
    </PageCard>
  );
}
