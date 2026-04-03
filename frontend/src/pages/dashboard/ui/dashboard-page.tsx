import { useCallback, useState } from "react";
import { KanbanBoard } from "@/features/kanban-board";
import { ApplicationPanel } from "@/features/application-panel";

/**
 * Dashboard page — renders the kanban board for managing job applications
 * and the application detail side panel. This is a `page/` because it maps
 * to a route (/dashboard) and composes features without FSD violations.
 *
 * State for selectedApplicationId lives here so both features can be wired
 * together at the page level (features must not import from each other).
 */
export function DashboardPage() {
  const [selectedApplicationId, setSelectedApplicationId] = useState<
    string | null
  >(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const handleCardClick = useCallback((id: string) => {
    setSelectedApplicationId(id);
  }, []);

  const handlePanelClose = useCallback(() => {
    setSelectedApplicationId(null);
  }, []);

  const handlePanelUpdate = useCallback(() => {
    setRefreshKey((k) => k + 1);
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
      <KanbanBoard onCardClick={handleCardClick} refreshKey={refreshKey} />
      <ApplicationPanel
        applicationId={selectedApplicationId}
        onClose={handlePanelClose}
        onUpdate={handlePanelUpdate}
      />
    </div>
  );
}
