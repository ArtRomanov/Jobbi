import { useDraggable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import type { Application } from "@/entities/application";
import { colors } from "@/shared/ui";
import { formatTimeAgo } from "../lib/format-time-ago";
import type { StatusKey } from "../lib/statuses";

interface ApplicationCardProps {
  application: Application;
  onClick: (id: string) => void;
  /** When true, renders the card without drag behavior (used in DragOverlay). */
  isOverlay?: boolean;
}

/**
 * A single kanban card displaying company, role, and relative update time.
 * Uses useDraggable from @dnd-kit for drag behavior.
 */
export function ApplicationCard({
  application,
  onClick,
  isOverlay = false,
}: ApplicationCardProps) {
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({
      id: application.id,
      data: { status: application.status },
      disabled: isOverlay,
    });

  const statusColor =
    colors.status[application.status as StatusKey] ?? colors.textMuted;

  const style: React.CSSProperties = {
    padding: "0.75rem",
    backgroundColor: colors.bgCard,
    borderRadius: "0.375rem",
    borderLeft: `3px solid ${statusColor}`,
    boxShadow: "0 1px 3px rgba(0, 0, 0, 0.08)",
    cursor: isDragging ? "grabbing" : "grab",
    opacity: isDragging ? 0.5 : 1,
    transform: transform ? CSS.Translate.toString(transform) : undefined,
    userSelect: "none",
  };

  return (
    <div
      ref={isOverlay ? undefined : setNodeRef}
      style={style}
      role="button"
      tabIndex={0}
      aria-label={`${application.company_name} — ${application.role_title}`}
      onClick={() => onClick(application.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick(application.id);
        }
      }}
      {...(isOverlay ? {} : { ...listeners, ...attributes })}
    >
      <div
        style={{
          fontWeight: 600,
          fontSize: "0.875rem",
          color: colors.textPrimary,
          marginBottom: "0.25rem",
        }}
      >
        {application.company_name}
      </div>
      <div
        style={{
          fontSize: "0.8125rem",
          color: colors.textSecondary,
          marginBottom: "0.375rem",
        }}
      >
        {application.role_title}
      </div>
      <div style={{ fontSize: "0.75rem", color: colors.textMuted }}>
        {formatTimeAgo(application.updated_at)}
      </div>
    </div>
  );
}
