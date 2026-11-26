/** The "What are you looking for?" drafts as the form holds them. */
export interface SearchSettingsDraft {
  description: string;
  keywords: readonly string[];
  keywordFilter: boolean;
}

/** Saved settings; fields the server left out count as empty / on. */
export interface SavedSearchSettings {
  description?: string | null;
  keywords?: readonly string[];
  keyword_filter?: boolean;
}

/** Trimmed description; blank and null are both "no description" (""). */
function normalizeDescription(value: string | null | undefined): string {
  return (value ?? "").trim();
}

/**
 * Keywords as the server stores them: trimmed, inner whitespace collapsed,
 * lowercased, de-duplicated keeping the first occurrence's place.
 */
export function normalizeKeywords(keywords: readonly string[]): string[] {
  const unique = new Set<string>();
  for (const keyword of keywords) {
    unique.add(keyword.split(/\s+/).filter(Boolean).join(" ").toLowerCase());
  }
  return [...unique];
}

function isSameList(first: readonly string[], second: readonly string[]): boolean {
  return first.length === second.length && first.every((item, index) => item === second[index]);
}

/**
 * True when saving the drafts would change what is saved. Compares after the
 * server's normalization, so re-typing "React" for a saved "react" or adding
 * spaces around the description is no change. Keyword order matters.
 */
export function hasSearchSettingsChanges(
  draft: SearchSettingsDraft,
  saved: SavedSearchSettings,
): boolean {
  if (draft.keywordFilter !== (saved.keyword_filter ?? true)) return true;
  if (normalizeDescription(draft.description) !== normalizeDescription(saved.description)) {
    return true;
  }
  return !isSameList(normalizeKeywords(draft.keywords), normalizeKeywords(saved.keywords ?? []));
}
