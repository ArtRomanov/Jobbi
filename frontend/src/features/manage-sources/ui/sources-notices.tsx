import type { DiscoveryStatus } from "@/entities/vacancy-source";
import { colors } from "@/shared/ui";
import { getStatusNotices } from "../lib/helpers";

interface SourcesNoticesProps {
  /** Null while loading: nothing is shown. */
  status: DiscoveryStatus | null;
}

/**
 * Daily-limit and AI-outage notices above the source list. The polite live
 * region is always mounted, so notices that appear after a poll are announced.
 */
export function SourcesNotices({ status }: SourcesNoticesProps) {
  const notices = getStatusNotices(status);

  return (
    <div
      role="status"
      aria-label="Vacancy search status"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.5rem",
        marginBottom: notices.length > 0 ? "1rem" : 0,
      }}
    >
      {notices.map((notice) => (
        <p
          key={notice}
          style={{
            margin: 0,
            padding: "0.5rem 0.75rem",
            borderRadius: "0.375rem",
            borderLeft: `3px solid ${colors.badge.warning.text}`,
            backgroundColor: colors.badge.warning.bg,
            color: colors.badge.warning.text,
            fontSize: "0.875rem",
            overflowWrap: "anywhere",
          }}
        >
          {notice}
        </p>
      ))}
    </div>
  );
}
