import { KanbanBoard } from "@/features/kanban-board";

/**
 * Dashboard page — renders the kanban board for managing job applications.
 * This is a `page/` because it maps to a route (/dashboard).
 */
export function DashboardPage() {
  return (
    <div
      style={{
        padding: "1.5rem",
        height: "calc(100vh - 4rem)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <KanbanBoard />
    </div>
  );
}
