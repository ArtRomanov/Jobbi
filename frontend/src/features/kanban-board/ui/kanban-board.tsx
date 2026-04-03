import { useCallback, useEffect, useMemo, useState } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { Link } from "react-router-dom";
import {
  listApplications,
  updateApplication,
  STATUSES,
  type Application,
} from "@/entities/application";
import { Button, colors, useToast } from "@/shared/ui";
import { ApplicationCard } from "./application-card";
import { KanbanColumn } from "./kanban-column";

interface KanbanBoardProps {
  /** Called when a card is clicked — parent uses this to open the detail panel. */
  onCardClick?: (id: string) => void;
  /** Increment to trigger a data re-fetch (e.g., after panel save/delete). */
  refreshKey?: number;
}

/**
 * Main kanban board — fetches applications and renders them in status columns.
 * Supports drag-and-drop between columns with optimistic status updates.
 *
 * This is a `feature/` because it encapsulates a user interaction (organizing
 * applications by status via drag-and-drop), not just a domain entity.
 */
export function KanbanBoard({
  onCardClick: onCardClickProp,
  refreshKey = 0,
}: KanbanBoardProps) {
  const [applications, setApplications] = useState<Application[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);

  const { showToast } = useToast();

  // Require a small drag distance before activating — prevents accidental drags on click
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  useEffect(() => {
    let cancelled = false;

    async function fetchApplications(): Promise<void> {
      try {
        const response = await listApplications({ per_page: 200 });
        if (!cancelled) {
          setApplications(response.items);
          setIsLoading(false);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load applications",
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

  // Group applications by status — one array per column
  const grouped = useMemo(() => {
    const map = new Map<string, Application[]>();
    for (const s of STATUSES) {
      map.set(s.key, []);
    }
    for (const app of applications) {
      const bucket = map.get(app.status);
      if (bucket) {
        bucket.push(app);
      }
    }
    return map;
  }, [applications]);

  const activeApplication = useMemo(
    () => (activeId ? applications.find((a) => a.id === activeId) : undefined),
    [activeId, applications],
  );

  const handleDragStart = useCallback((event: DragStartEvent) => {
    setActiveId(String(event.active.id));
  }, []);

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      setActiveId(null);

      const { active, over } = event;
      if (!over) return;

      const cardId = String(active.id);
      const previousStatus = (active.data.current as { status: string })
        .status;
      const newStatus = String(over.id);

      if (previousStatus === newStatus) return;

      // Optimistic update — move the card immediately
      setApplications((prev) =>
        prev.map((app) =>
          app.id === cardId ? { ...app, status: newStatus } : app,
        ),
      );

      // Persist to backend; roll back on failure
      updateApplication(cardId, { status: newStatus }).catch(
        (err: unknown) => {
          setApplications((prev) =>
            prev.map((app) =>
              app.id === cardId ? { ...app, status: previousStatus } : app,
            ),
          );
          showToast(
            err instanceof Error
              ? err.message
              : "Failed to update application status",
            "error",
          );
        },
      );
    },
    [showToast],
  );

  const handleCardClick = useCallback(
    (id: string) => {
      onCardClickProp?.(id);
    },
    [onCardClickProp],
  );

  // --- Loading state ---
  if (isLoading) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "40vh",
          color: colors.textMuted,
          fontSize: "0.875rem",
        }}
      >
        Loading applications...
      </div>
    );
  }

  // --- Error state ---
  if (error) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "40vh",
          gap: "0.75rem",
        }}
      >
        <p style={{ color: colors.error, fontSize: "0.875rem" }}>{error}</p>
        <Button
          variant="secondary"
          onClick={() => {
            setError(null);
            setIsLoading(true);
            listApplications({ per_page: 200 })
              .then((res) => {
                setApplications(res.items);
                setIsLoading(false);
              })
              .catch((err: unknown) => {
                setError(
                  err instanceof Error
                    ? err.message
                    : "Failed to load applications",
                );
                setIsLoading(false);
              });
          }}
        >
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Toolbar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "1rem",
        }}
      >
        <h1
          style={{
            fontSize: "1.25rem",
            fontWeight: 700,
            color: colors.textPrimary,
            margin: 0,
          }}
        >
          Applications
        </h1>
        <Link to="/new-application" style={{ textDecoration: "none" }}>
          <Button>New Application</Button>
        </Link>
      </div>

      {/* Board */}
      <DndContext
        sensors={sensors}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      >
        <div
          style={{
            display: "flex",
            gap: "0.75rem",
            flex: 1,
            overflowX: "auto",
            paddingBottom: "0.5rem",
          }}
        >
          {STATUSES.map((s) => (
            <KanbanColumn
              key={s.key}
              status={s.key}
              label={s.label}
              applications={grouped.get(s.key) ?? []}
              onCardClick={handleCardClick}
            />
          ))}
        </div>

        <DragOverlay dropAnimation={null}>
          {activeApplication ? (
            <ApplicationCard
              application={activeApplication}
              onClick={handleCardClick}
              isOverlay
            />
          ) : null}
        </DragOverlay>
      </DndContext>
    </div>
  );
}
