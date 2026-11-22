interface AppendUniqueTermsOptions {
  /** Stop adding once the list holds this many terms. */
  maxItems?: number;
  /** Longer terms are cut to this many characters (like typing into a maxLength input). */
  maxLength?: number;
}

/**
 * Add raw terms to a list: each one is trimmed (and cut to `maxLength`), empty
 * ones are skipped, and so are case-insensitive duplicates of terms already in
 * the list or earlier in `rawTerms`. Returns the original array when nothing
 * was added, so callers can skip a state update.
 */
export function appendUniqueTerms(
  values: readonly string[],
  rawTerms: readonly string[],
  { maxItems = Number.POSITIVE_INFINITY, maxLength }: AppendUniqueTermsOptions = {},
): readonly string[] {
  const seen = new Set(values.map((value) => value.toLowerCase()));
  const added: string[] = [];

  for (const raw of rawTerms) {
    if (values.length + added.length >= maxItems) break;
    const term = (maxLength === undefined ? raw.trim() : raw.trim().slice(0, maxLength)).trim();
    const key = term.toLowerCase();
    if (term === "" || seen.has(key)) continue;
    seen.add(key);
    added.push(term);
  }

  return added.length === 0 ? values : [...values, ...added];
}
