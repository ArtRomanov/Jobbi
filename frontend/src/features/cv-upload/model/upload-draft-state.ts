/** The text extracted from an uploaded file, not saved yet (spec 011 §2.3). */
export interface UploadDraft {
  name: string;
  content: string;
  truncated: boolean;
}

/** Router state passed to `/cvs/new` after a successful upload. */
export interface UploadDraftRouterState {
  uploadDraft: UploadDraft;
}

/** Reads the draft from `location.state`; anything else (or nothing) is `null`. */
export function readUploadDraft(state: unknown): UploadDraft | null {
  if (typeof state !== "object" || state === null || !("uploadDraft" in state)) {
    return null;
  }
  const draft: unknown = (state as { uploadDraft: unknown }).uploadDraft;
  if (typeof draft !== "object" || draft === null) return null;
  const { name, content, truncated } = draft as Record<string, unknown>;
  if (typeof name !== "string" || typeof content !== "string") return null;
  return { name, content, truncated: truncated === true };
}
