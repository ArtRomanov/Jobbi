import type { RemovedVacancySource, VacancySource } from "@/entities/vacancy-source";
import type { InboxFilterValues, SourceOption } from "../model/types";
import {
  ALL_SOURCES_LABEL,
  ALL_SOURCES_VALUE,
  DEFAULT_INBOX_FILTERS,
  FORWARDED_SOURCE_KEY_PREFIX,
  FORWARDED_SOURCE_SUFFIX,
  REMOVED_SOURCE_SUFFIX,
} from "./constants";

function inactiveSourceSuffix(key: string): string {
  return key.startsWith(FORWARDED_SOURCE_KEY_PREFIX) ? FORWARDED_SOURCE_SUFFIX : REMOVED_SOURCE_SUFFIX;
}

/**
 * Options of the Source select: "All sources", live sources, then sources
 * that only old cards still carry, labelled "(removed)" — or "(forwarded)"
 * for channels whose posts the user forwarded to the bot. Values are source
 * keys, so a removed and re-added source is one option. A selected key that
 * is in neither list (e.g. its last card just left) keeps an option, so the
 * select never shows a value that is not applied.
 */
export function buildSourceOptions(
  sources: readonly VacancySource[],
  removedSources: readonly RemovedVacancySource[],
  selected: string | null,
): SourceOption[] {
  const options: SourceOption[] = [{ value: ALL_SOURCES_VALUE, label: ALL_SOURCES_LABEL }];
  const known = new Set<string>();
  for (const source of sources) {
    if (known.has(source.key)) continue;
    known.add(source.key);
    options.push({ value: source.key, label: source.display_name });
  }
  for (const removed of removedSources) {
    if (known.has(removed.key)) continue;
    known.add(removed.key);
    options.push({ value: removed.key, label: `${removed.label}${inactiveSourceSuffix(removed.key)}` });
  }
  if (selected !== null && !known.has(selected)) {
    options.push({ value: selected, label: `${selected}${inactiveSourceSuffix(selected)}` });
  }
  return options;
}

/** True when any filter differs from the defaults (sort does not filter). */
export function hasActiveFilters(values: InboxFilterValues): boolean {
  return values.source !== DEFAULT_INBOX_FILTERS.source || values.state !== DEFAULT_INBOX_FILTERS.state;
}
