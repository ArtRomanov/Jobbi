import type { DiscoveryStatus, VacancySource, VacancySourceKind } from "@/entities/vacancy-source";
import { formatTimeAgo } from "@/shared/lib";
import {
  AI_UNAVAILABLE_NOTICE,
  LAST_CHECKED_PREFIX,
  PENDING_COUNT_PREFIX,
  WATCHING_SINCE_PREFIX,
  SCAN_POLL_INTERVAL_MS,
  STATUS_POLL_INTERVAL_MS,
} from "./constants";

/**
 * Which source should receive focus after `removedId` is removed: the next one
 * in display order, else the previous one, else null (list is now empty).
 * `isPresent` filters out ids that are gone already (e.g. concurrent removes).
 */
export function pickFocusAfterRemove(
  orderedIds: readonly string[],
  removedId: string,
  isPresent: (id: string) => boolean,
): string | null {
  const index = orderedIds.indexOf(removedId);
  const isCandidate = (id: string): boolean => id !== removedId && isPresent(id);

  for (let i = index + 1; i < orderedIds.length; i += 1) {
    const id = orderedIds[i];
    if (id !== undefined && isCandidate(id)) return id;
  }
  for (let i = index - 1; i >= 0; i -= 1) {
    const id = orderedIds[i];
    if (id !== undefined && isCandidate(id)) return id;
  }
  return null;
}

/**
 * Apply polled status fields to the local list. Membership stays local, so a
 * poll that started before an add/remove can never undo it. Rows missing from
 * `polled` keep their local copy (the caller drops rows saved mid-poll).
 */
export function mergePolledSources(
  current: readonly VacancySource[],
  polled: readonly VacancySource[],
): VacancySource[] {
  const byId = new Map(polled.map((source) => [source.id, source]));
  return current.map((source) => {
    const fresh = byId.get(source.id);
    return fresh
      ? {
          ...source,
          scanning: fresh.scanning,
          last_checked_at: fresh.last_checked_at,
          unavailable: fresh.unavailable,
          last_error: fresh.last_error,
          watching_since: fresh.watching_since,
          editable: fresh.editable,
          pending_count: fresh.pending_count,
        }
      : source;
  });
}

/** True when a source that was scanning in `before` is present and not scanning in `after`. */
export function hasScanFinished(
  before: readonly VacancySource[],
  after: readonly VacancySource[],
): boolean {
  const scanningAfter = new Map(after.map((source) => [source.id, source.scanning]));
  return before.some((source) => source.scanning && scanningAfter.get(source.id) === false);
}

/** "Daily limit reached — N posts are waiting" ("1 post is waiting" for one). */
export function formatLimitNotice(waitingCount: number): string {
  const waiting = waitingCount === 1 ? "1 post is waiting" : `${waitingCount} posts are waiting`;
  return `Daily limit reached — ${waiting}`;
}

/** Status notices to show above the source list, in display order (may be empty). */
export function getStatusNotices(status: DiscoveryStatus | null): string[] {
  if (status === null) return [];
  const notices: string[] = [];
  if (status.limit_reached) notices.push(formatLimitNotice(status.waiting_count));
  if (status.ai_unavailable) notices.push(AI_UNAVAILABLE_NOTICE);
  return notices;
}

/** Next poll delay: fast while a source scans, slow otherwise. */
export function getPollInterval(isAnyScanning: boolean): number {
  return isAnyScanning ? SCAN_POLL_INTERVAL_MS : STATUS_POLL_INTERVAL_MS;
}

/** "Found N vacancies" ("Found 1 vacancy"). */
export function formatFoundCount(count: number): string {
  return `Found ${count} ${count === 1 ? "vacancy" : "vacancies"}`;
}

/**
 * Check status after the kind label: "Watching since <time>" for a web page not
 * checked since it was saved, else "Last checked <time>", else null (never
 * checked). Scanning is handled by the caller.
 */
export function getCheckedLabel(source: VacancySource): string | null {
  const { kind, last_checked_at: lastCheckedAt, watching_since: watchingSince } = source;
  if (kind === "web" && watchingSince && (lastCheckedAt === null || lastCheckedAt === watchingSince)) {
    return `${WATCHING_SINCE_PREFIX} ${formatTimeAgo(watchingSince)}`;
  }
  return lastCheckedAt ? `${LAST_CHECKED_PREFIX} ${formatTimeAgo(lastCheckedAt)}` : null;
}

/** "Waiting for AI: N" for a source with posts waiting to be rated, else null. */
export function getPendingLabel(pendingCount: number): string | null {
  return pendingCount > 0 ? `${PENDING_COUNT_PREFIX} ${pendingCount}` : null;
}

/** Board link templates per kind (`{handle}` = the part of `key` after "kind:"). */
const BOARD_LINK_TEMPLATES: Record<Exclude<VacancySourceKind, "telegram" | "web">, string> = {
  greenhouse: "https://job-boards.greenhouse.io/{handle}",
  lever: "https://jobs.lever.co/{handle}",
  lever_eu: "https://jobs.eu.lever.co/{handle}",
  teamtailor: "https://{handle}.teamtailor.com",
  ashby: "https://jobs.ashbyhq.com/{handle}",
};

/**
 * The link the Edit dialog starts with: the saved URL of a web page,
 * `@handle` for Telegram, the board link for Greenhouse / Lever / Teamtailor / Ashby.
 * The handle comes from `key` ("<kind>:<handle>").
 */
export function getSourceLink(source: Pick<VacancySource, "kind" | "key" | "url">): string {
  if (source.kind === "web") return source.url ?? "";
  const separator = source.key.indexOf(":");
  const handle = separator === -1 ? source.key : source.key.slice(separator + 1);
  if (source.kind === "telegram") return `@${handle}`;
  return BOARD_LINK_TEMPLATES[source.kind].replace("{handle}", handle);
}
