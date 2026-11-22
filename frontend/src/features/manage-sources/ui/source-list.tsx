import type { VacancySource } from "@/entities/vacancy-source";
import { colors } from "@/shared/ui";
import { NO_SOURCES_MESSAGE } from "../lib/constants";
import { SourceListItem } from "./source-list-item";

interface SourceListProps {
  sources: readonly VacancySource[];
  removingIds: ReadonlySet<string>;
  onRemove: (id: string) => void;
  onRegisterRemoveButton: (id: string, element: HTMLButtonElement | null) => void;
}

/** Watched sources, or a short hint when there are none. */
export function SourceList({
  sources,
  removingIds,
  onRemove,
  onRegisterRemoveButton,
}: SourceListProps) {
  if (sources.length === 0) {
    return <p style={{ fontSize: "0.875rem", color: colors.textMuted }}>{NO_SOURCES_MESSAGE}</p>;
  }

  return (
    <ul aria-label="Watched sources" style={{ listStyle: "none", margin: 0, padding: 0 }}>
      {sources.map((source) => (
        <SourceListItem
          key={source.id}
          source={source}
          isRemoving={removingIds.has(source.id)}
          onRemove={onRemove}
          onRegisterRemoveButton={onRegisterRemoveButton}
        />
      ))}
    </ul>
  );
}
