import { useCallback, useEffect, useState } from "react";
import {
  getHistory,
  type StatusHistoryFeed,
  type StatusKey,
} from "@/entities/application";
import { colors } from "@/shared/ui";
import { formatTimeAgo } from "@/shared/lib";
import { FEED_PAGE_SIZE } from "../lib/constants";

interface ActivityFeedProps {
  onApplicationClick: (id: string) => void;
}

/**
 * Chronological feed of status change events, newest first.
 * Each entry shows company, role, new status, and relative time.
 *
 * Supports "Load more" pagination to fetch additional history pages.
 */
export function ActivityFeed({ onApplicationClick }: ActivityFeedProps) {
  const [entries, setEntries] = useState<StatusHistoryFeed[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchFirstPage(): Promise<void> {
      try {
        setIsLoading(true);
        const response = await getHistory({
          page: 1,
          per_page: FEED_PAGE_SIZE,
        });
        if (!cancelled) {
          setEntries(response.items);
          setHasMore(response.items.length < response.total);
          setPage(1);
          setIsLoading(false);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load activity feed",
          );
          setIsLoading(false);
        }
      }
    }

    void fetchFirstPage();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleLoadMore = useCallback(async () => {
    const nextPage = page + 1;
    setIsLoadingMore(true);
    try {
      const response = await getHistory({
        page: nextPage,
        per_page: FEED_PAGE_SIZE,
      });
      setEntries((prev) => [...prev, ...response.items]);
      setHasMore(nextPage * FEED_PAGE_SIZE < response.total);
      setPage(nextPage);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to load more entries",
      );
    } finally {
      setIsLoadingMore(false);
    }
  }, [page]);

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
        Loading activity...
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

  if (entries.length === 0) {
    return (
      <div
        style={{
          padding: "2rem",
          textAlign: "center",
          color: colors.textMuted,
          fontSize: "0.875rem",
        }}
      >
        No activity yet.
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
        Recent Activity
      </h2>

      <div style={{ display: "flex", flexDirection: "column" }}>
        {entries.map((entry, index) => {
          const statusColor =
            colors.status[entry.status as StatusKey] ?? colors.textMuted;
          const isLast = index === entries.length - 1;

          return (
            <div
              key={entry.id}
              role="button"
              tabIndex={0}
              onClick={() => onApplicationClick(entry.application_id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onApplicationClick(entry.application_id);
                }
              }}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "0.75rem",
                padding: "0.625rem 0.5rem",
                borderBottom: isLast
                  ? "none"
                  : `1px solid ${colors.borderLight}`,
                cursor: "pointer",
                borderRadius: "0.25rem",
                transition: "background-color 0.15s",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = colors.bgDisabled;
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = "transparent";
              }}
            >
              {/* Colored dot */}
              <div
                style={{
                  width: "0.5rem",
                  height: "0.5rem",
                  borderRadius: "50%",
                  backgroundColor: statusColor,
                  marginTop: "0.375rem",
                  flexShrink: 0,
                }}
                aria-hidden="true"
              />

              {/* Entry text */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <span
                  style={{
                    fontSize: "0.8125rem",
                    color: colors.textPrimary,
                    lineHeight: 1.4,
                  }}
                >
                  <strong>{entry.company_name}</strong>
                  {" \u2014 "}
                  {entry.role_title}
                  {" moved to "}
                  <span style={{ color: statusColor, fontWeight: 500 }}>
                    {entry.status}
                  </span>
                </span>
              </div>

              {/* Relative time */}
              <div
                style={{
                  fontSize: "0.75rem",
                  color: colors.textMuted,
                  flexShrink: 0,
                  whiteSpace: "nowrap",
                }}
              >
                {formatTimeAgo(entry.changed_at)}
              </div>
            </div>
          );
        })}
      </div>

      {hasMore && (
        <div style={{ textAlign: "center", padding: "0.75rem 0" }}>
          <button
            type="button"
            onClick={() => void handleLoadMore()}
            disabled={isLoadingMore}
            style={{
              padding: "0.375rem 1rem",
              fontSize: "0.8125rem",
              fontWeight: 500,
              color: colors.primary,
              backgroundColor: "transparent",
              border: `1px solid ${colors.primary}`,
              borderRadius: "0.375rem",
              cursor: isLoadingMore ? "not-allowed" : "pointer",
              opacity: isLoadingMore ? 0.6 : 1,
            }}
          >
            {isLoadingMore ? "Loading..." : "Load more"}
          </button>
        </div>
      )}
    </div>
  );
}
