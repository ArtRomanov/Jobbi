import { useCallback, useState } from "react";
import { KanbanBoard } from "@/features/kanban-board";
import { ApplicationPanel } from "@/features/application-panel";
import { STATUSES, type StatusKey } from "@/entities/application";
import { colors } from "@/shared/ui";
import { useDebounce } from "@/shared/lib";
import { SEARCH_DEBOUNCE_MS } from "../lib/constants";

/**
 * Dashboard page — renders the kanban board for managing job applications
 * and the application detail side panel. This is a `page/` because it maps
 * to a route (/dashboard) and composes features without FSD violations.
 *
 * State for selectedApplicationId lives here so both features can be wired
 * together at the page level (features must not import from each other).
 *
 * Search and column visibility controls live here (page layer composes
 * features) — the KanbanBoard receives them as props.
 */
export function DashboardPage() {
  const [selectedApplicationId, setSelectedApplicationId] = useState<
    string | null
  >(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // Search state — debounced before passing to the board
  const [searchInput, setSearchInput] = useState("");
  const debouncedSearch = useDebounce(searchInput, SEARCH_DEBOUNCE_MS);

  // Column visibility — local state, all visible by default
  const [hiddenStatuses, setHiddenStatuses] = useState<readonly StatusKey[]>(
    [],
  );

  const handleCardClick = useCallback((id: string) => {
    setSelectedApplicationId(id);
  }, []);

  const handlePanelClose = useCallback(() => {
    setSelectedApplicationId(null);
  }, []);

  const handlePanelUpdate = useCallback(() => {
    setRefreshKey((k) => k + 1);
  }, []);

  const toggleStatus = useCallback((key: StatusKey) => {
    setHiddenStatuses((prev) =>
      prev.includes(key) ? prev.filter((s) => s !== key) : [...prev, key],
    );
  }, []);

  return (
    <div
      style={{
        padding: "1.5rem",
        height: "calc(100vh - 4rem)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Toolbar — search + column visibility toggles */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.75rem",
          paddingBottom: "0.75rem",
          marginBottom: "0.75rem",
          borderBottom: `1px solid ${colors.borderLight}`,
        }}
      >
        {/* Search input */}
        <input
          type="text"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Search by company or role..."
          aria-label="Search applications"
          style={{
            width: "100%",
            padding: "0.5rem 0.75rem",
            border: `1px solid ${colors.border}`,
            borderRadius: "0.375rem",
            fontSize: "0.875rem",
            outline: "none",
            boxSizing: "border-box",
            color: colors.textPrimary,
          }}
        />

        {/* Column visibility toggles */}
        <div
          style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}
          role="group"
          aria-label="Column visibility"
        >
          {STATUSES.map((s) => {
            const isHidden = hiddenStatuses.includes(s.key);
            const statusColor =
              colors.status[s.key as keyof typeof colors.status];

            return (
              <button
                key={s.key}
                type="button"
                onClick={() => toggleStatus(s.key)}
                aria-pressed={!isHidden}
                style={{
                  padding: "0.25rem 0.625rem",
                  fontSize: "0.75rem",
                  fontWeight: 500,
                  borderRadius: "9999px",
                  border: "none",
                  cursor: "pointer",
                  transition: "background-color 0.15s, color 0.15s",
                  backgroundColor: isHidden
                    ? colors.bgDisabled
                    : statusColor,
                  color: isHidden ? colors.textMuted : "#ffffff",
                }}
              >
                {s.label}
              </button>
            );
          })}
        </div>
      </div>

      <KanbanBoard
        onCardClick={handleCardClick}
        refreshKey={refreshKey}
        searchQuery={debouncedSearch}
        hiddenStatuses={hiddenStatuses}
      />
      <ApplicationPanel
        applicationId={selectedApplicationId}
        onClose={handlePanelClose}
        onUpdate={handlePanelUpdate}
      />
    </div>
  );
}
