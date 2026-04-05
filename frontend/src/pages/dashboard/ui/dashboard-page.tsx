import { useCallback, useState } from "react";
import { KanbanBoard } from "@/features/kanban-board";
import { ApplicationPanel } from "@/features/application-panel";
import { ActivityFeed, ApplicationList } from "@/features/timeline-feed";
import { STATUSES, type StatusKey } from "@/entities/application";
import { colors } from "@/shared/ui";
import { useDebounce } from "@/shared/lib";
import { SEARCH_DEBOUNCE_MS } from "../lib/constants";

type DashboardTab = "board" | "timeline";

/**
 * Dashboard page — renders the kanban board or timeline view for managing job
 * applications, plus the application detail side panel. This is a `page/`
 * because it maps to a route (/dashboard) and composes features without FSD
 * violations.
 *
 * A tab toggle lets the user switch between "Board" (kanban) and "Timeline"
 * (activity feed + application list) views. Both views share the same
 * ApplicationPanel for viewing/editing details.
 */
export function DashboardPage() {
  const [activeTab, setActiveTab] = useState<DashboardTab>("board");

  const [selectedApplicationId, setSelectedApplicationId] = useState<
    string | null
  >(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // Search state — debounced before passing to the board (Board tab only)
  const [searchInput, setSearchInput] = useState("");
  const debouncedSearch = useDebounce(searchInput, SEARCH_DEBOUNCE_MS);

  // Column visibility — local state, all visible by default (Board tab only)
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
      {/* Tab toggle */}
      <div
        style={{
          display: "flex",
          gap: "0",
          marginBottom: "0.75rem",
        }}
        role="tablist"
        aria-label="Dashboard view"
      >
        <TabButton
          label="Board"
          isActive={activeTab === "board"}
          onClick={() => setActiveTab("board")}
        />
        <TabButton
          label="Timeline"
          isActive={activeTab === "timeline"}
          onClick={() => setActiveTab("timeline")}
        />
      </div>

      {/* Board toolbar — search + column visibility (Board tab only) */}
      {activeTab === "board" && (
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
      )}

      {/* Tab content */}
      {activeTab === "board" ? (
        <KanbanBoard
          onCardClick={handleCardClick}
          refreshKey={refreshKey}
          searchQuery={debouncedSearch}
          hiddenStatuses={hiddenStatuses}
        />
      ) : (
        <div
          style={{
            flex: 1,
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
            gap: "1.5rem",
          }}
        >
          <ActivityFeed onApplicationClick={handleCardClick} />
          <ApplicationList
            onApplicationClick={handleCardClick}
            refreshKey={refreshKey}
          />
        </div>
      )}

      <ApplicationPanel
        applicationId={selectedApplicationId}
        onClose={handlePanelClose}
        onUpdate={handlePanelUpdate}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Internal sub-component — tab button (not exported, page-internal) */
/* ------------------------------------------------------------------ */

interface TabButtonProps {
  label: string;
  isActive: boolean;
  onClick: () => void;
}

function TabButton({ label, isActive, onClick }: TabButtonProps) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={isActive}
      onClick={onClick}
      style={{
        padding: "0.5rem 1.25rem",
        fontSize: "0.875rem",
        fontWeight: isActive ? 600 : 400,
        color: isActive ? colors.primary : colors.textMuted,
        backgroundColor: "transparent",
        border: "none",
        borderBottom: `2px solid ${isActive ? colors.primary : "transparent"}`,
        cursor: "pointer",
        transition: "color 0.15s, border-color 0.15s",
      }}
    >
      {label}
    </button>
  );
}
