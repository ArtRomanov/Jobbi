import { useEffect, useMemo, useState } from "react";
import {
  listApplications,
  STATUSES,
  type Application,
  type StatusKey,
} from "@/entities/application";
import { colors } from "@/shared/ui";
import { formatTimeAgo } from "@/shared/lib";
import { LIST_PAGE_SIZE } from "../lib/constants";

interface ApplicationListProps {
  onApplicationClick: (id: string) => void;
  refreshKey?: number;
}

/** Map status keys to their human-readable labels. */
const STATUS_LABELS: Map<string, string> = new Map(
  STATUSES.map((s) => [s.key, s.label]),
);

/**
 * Tabular list of all applications sorted by last updated (API default).
 * Each row shows company, role, status badge, and relative update time.
 * Clicking a row opens the application detail panel.
 */
export function ApplicationList({
  onApplicationClick,
  refreshKey = 0,
}: ApplicationListProps) {
  const [applications, setApplications] = useState<Application[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchApplications(): Promise<void> {
      try {
        setIsLoading(true);
        const response = await listApplications({ per_page: LIST_PAGE_SIZE });
        if (!cancelled) {
          setApplications(response.items);
          setIsLoading(false);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Failed to load applications",
          );
          setIsLoading(false);
        }
      }
    }

    void fetchApplications();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const rows = useMemo(() => applications, [applications]);

  if (isLoading) {
    return (
      <div
        style={{
          padding: "2rem",
          textAlign: "center",
          color: colors.textMuted,
          fontSize: "0.875rem",
        }}
      >
        Loading applications...
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          padding: "1rem",
          color: colors.error,
          fontSize: "0.875rem",
        }}
      >
        {error}
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div
        style={{
          padding: "2rem",
          textAlign: "center",
          color: colors.textMuted,
          fontSize: "0.875rem",
        }}
      >
        No applications yet.
      </div>
    );
  }

  return (
    <div>
      <h2
        style={{
          fontSize: "0.9375rem",
          fontWeight: 600,
          color: colors.textPrimary,
          margin: "0 0 0.75rem",
        }}
      >
        All Applications
      </h2>

      {/* Header row */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 8rem 7rem",
          gap: "0.5rem",
          padding: "0.5rem 0.75rem",
          fontSize: "0.75rem",
          fontWeight: 600,
          color: colors.textMuted,
          textTransform: "uppercase",
          letterSpacing: "0.03em",
          borderBottom: `1px solid ${colors.border}`,
        }}
      >
        <div>Company</div>
        <div>Role</div>
        <div>Status</div>
        <div>Updated</div>
      </div>

      {/* Data rows */}
      {rows.map((app) => {
        const statusColor =
          colors.status[app.status as StatusKey] ?? colors.textMuted;
        const statusLabel = STATUS_LABELS.get(app.status) ?? app.status;

        return (
          <div
            key={app.id}
            role="button"
            tabIndex={0}
            onClick={() => onApplicationClick(app.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onApplicationClick(app.id);
              }
            }}
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr 8rem 7rem",
              gap: "0.5rem",
              padding: "0.625rem 0.75rem",
              fontSize: "0.8125rem",
              color: colors.textPrimary,
              borderBottom: `1px solid ${colors.borderLight}`,
              cursor: "pointer",
              transition: "background-color 0.15s",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = colors.bgDisabled;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = "transparent";
            }}
          >
            <div
              style={{
                fontWeight: 500,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {app.company_name}
            </div>
            <div
              style={{
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                color: colors.textSecondary,
              }}
            >
              {app.role_title}
            </div>
            <div>
              <span
                style={{
                  display: "inline-block",
                  padding: "0.125rem 0.5rem",
                  fontSize: "0.6875rem",
                  fontWeight: 500,
                  borderRadius: "9999px",
                  backgroundColor: statusColor,
                  color: "#ffffff",
                }}
              >
                {statusLabel}
              </span>
            </div>
            <div
              style={{
                fontSize: "0.75rem",
                color: colors.textMuted,
              }}
            >
              {formatTimeAgo(app.updated_at)}
            </div>
          </div>
        );
      })}
    </div>
  );
}
