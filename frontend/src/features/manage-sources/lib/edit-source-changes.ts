/** Raw Edit-dialog field values (what the inputs hold). */
export interface EditSourceDraft {
  name: string;
  link: string;
  jobLinkContains: string;
}

/**
 * True when saving the Edit dialog would change the source. Mirrors
 * `editSourceSchema` (every field trimmed, blank name / pattern = none), so
 * spaces alone are no change. The pattern only counts for a web page.
 */
export function hasEditSourceChanges(
  draft: EditSourceDraft,
  initial: EditSourceDraft,
  isWeb: boolean,
): boolean {
  return (
    draft.name.trim() !== initial.name.trim() ||
    draft.link.trim() !== initial.link.trim() ||
    (isWeb && draft.jobLinkContains.trim() !== initial.jobLinkContains.trim())
  );
}
