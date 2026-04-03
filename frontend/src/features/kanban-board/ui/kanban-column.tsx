import { useDroppable } from "@dnd-kit/core";
import type { Application } from "@/entities/application";
import { colors } from "@/shared/ui";
import type { StatusKey } from "../lib/statuses";
import { ApplicationCard } from "./application-card";

interface KanbanColumnProps {
  status: string;
  label: string;
  applications: Application[];
  onCardClick: (id: string) => void;
}

/**
 * A single status column in the kanban board.
 * Acts as a droppable target via @dnd-kit's useDroppable.
 */
export function KanbanColumn({
  status,
  label,
  applications,
  onCardClick,
}: KanbanColumnProps) {
  const { isOver, setNodeRef } = useDroppable({ id: status });

  const statusColor = colors.status[status as StatusKey] ?? colors.textMuted;

  return (
    <div
      style={{
        width: 280,
        minWidth: 280,
        display: "flex",
        flexDirection: "column",
        backgroundColor: colors.bgPage,
        borderRadius: "0.5rem",
        border: `1px solid ${colors.borderLight}`,
        maxHeight: "100%",
      }}
    >
      {/* Column header */}
      <div
        style={{
          padding: "0.75rem",
          borderBottom: `1px solid ${colors.borderLight}`,
          backgroundColor: `${statusColor}10`,
          borderRadius: "0.5rem 0.5rem 0 0",
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
        }}
      >
        <div
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            backgroundColor: statusColor,
            flexShrink: 0,
          }}
        />
        <span
          style={{
            fontWeight: 600,
            fontSize: "0.875rem",
            color: colors.textPrimary,
          }}
        >
          {label}
        </span>
        <span
          style={{
            fontSize: "0.75rem",
            color: colors.textMuted,
            backgroundColor: colors.bgDisabled,
            padding: "0.125rem 0.5rem",
            borderRadius: "9999px",
            marginLeft: "auto",
          }}
        >
          {applications.length}
        </span>
      </div>

      {/* Droppable area */}
      <div
        ref={setNodeRef}
        style={{
          flex: 1,
          padding: "0.5rem",
          display: "flex",
          flexDirection: "column",
          gap: "0.5rem",
          overflowY: "auto",
          minHeight: 80,
          backgroundColor: isOver ? `${statusColor}08` : undefined,
          transition: "background-color 150ms ease",
        }}
      >
        {applications.length === 0 ? (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              minHeight: 60,
              color: colors.textPlaceholder,
              fontSize: "0.8125rem",
            }}
          >
            No applications
          </div>
        ) : (
          applications.map((app) => (
            <ApplicationCard
              key={app.id}
              application={app}
              onClick={onCardClick}
            />
          ))
        )}
      </div>
    </div>
  );
}
