import { memo, useMemo } from "react";
import { FormSelect, SegmentedControl } from "@/shared/ui";
import type { RemovedVacancySource, VacancySource } from "@/entities/vacancy-source";
import { ALL_SOURCES_VALUE, SORT_OPTIONS, STATE_OPTIONS } from "../lib/constants";
import { buildSourceOptions } from "../lib/helpers";
import type { InboxFilterValues } from "../model/types";

interface InboxFiltersProps {
  value: InboxFilterValues;
  onChange: (value: InboxFilterValues) => void;
  sources: readonly VacancySource[];
  /** Sources that only existing cards still reference; shown with "(removed)". */
  removedSources: readonly RemovedVacancySource[];
}

/** Controlled Inbox filter bar: source, new/seen/all and sort. Filters combine. */
export const InboxFilters = memo(function InboxFilters({
  value,
  onChange,
  sources,
  removedSources,
}: InboxFiltersProps) {
  const sourceOptions = useMemo(
    () => buildSourceOptions(sources, removedSources, value.source),
    [sources, removedSources, value.source],
  );

  return (
    <div
      role="group"
      aria-label="Filter vacancies"
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "flex-end",
        gap: "0.75rem",
      }}
    >
      {/* FormSelect brings its own 1rem bottom margin; the controls match it */}
      <div style={{ flex: "1 1 12rem", minWidth: 0 }}>
        <FormSelect
          label="Source"
          options={sourceOptions}
          value={value.source ?? ALL_SOURCES_VALUE}
          onChange={(event) => {
            const next = event.target.value;
            onChange({ ...value, source: next === ALL_SOURCES_VALUE ? null : next });
          }}
        />
      </div>
      <div style={{ marginBottom: "1rem" }}>
        <SegmentedControl
          label="Show"
          options={STATE_OPTIONS}
          value={value.state}
          onChange={(state) => onChange({ ...value, state })}
        />
      </div>
      <div style={{ marginBottom: "1rem" }}>
        <SegmentedControl
          label="Sort"
          options={SORT_OPTIONS}
          value={value.sort}
          onChange={(sort) => onChange({ ...value, sort })}
        />
      </div>
    </div>
  );
});
