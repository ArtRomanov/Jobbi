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

/**
 * Exactly Python's `str.isspace()` set, which the server's `str.strip()` /
 * `str.split()` use. Not JS `\s` / `trim()`: those also treat U+FEFF as
 * whitespace and miss U+001C–U+001F and U+0085.
 */
const PY_WHITESPACE =
  "\\t\\n\\v\\f\\r\\u001c-\\u001f \\u0085\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const PY_WHITESPACE_RUN = new RegExp(`[${PY_WHITESPACE}]+`);
const PY_EDGE_WHITESPACE = new RegExp(`^[${PY_WHITESPACE}]+|[${PY_WHITESPACE}]+$`, "g");

/** Python's `str.strip()`. */
function pyStrip(value: string): string {
  return value.replace(PY_EDGE_WHITESPACE, "");
}

/** Python's `str.split()` (no argument): split on whitespace runs, drop empties. */
function pySplit(value: string): string[] {
  return value.split(PY_WHITESPACE_RUN).filter(Boolean);
}

/** Trimmed description; blank and null are both "no description" (""). */
function normalizeDescription(value: string | null | undefined): string {
  return pyStrip(value ?? "");
}

/**
 * Keywords as the server stores them: trimmed, inner whitespace collapsed,
 * lowercased, de-duplicated keeping the first occurrence's place.
 */
export function normalizeKeywords(keywords: readonly string[]): string[] {
  const unique = new Set<string>();
  for (const keyword of keywords) {
    unique.add(pySplit(keyword).join(" ").toLowerCase());
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
