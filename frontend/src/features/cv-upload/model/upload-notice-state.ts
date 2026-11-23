/** What the editor needs to know about the upload that just created the CV. */
export interface UploadNoticeData {
  truncated: boolean;
  becameBase: boolean;
}

/** Router state passed to `/cvs/<id>/edit` after a successful upload. */
export interface UploadNoticeRouterState {
  uploadNotice: UploadNoticeData;
}

/** Reads the notice from `location.state`; anything else (or nothing) is `null`. */
export function readUploadNotice(state: unknown): UploadNoticeData | null {
  if (typeof state !== "object" || state === null || !("uploadNotice" in state)) {
    return null;
  }
  const notice: unknown = (state as { uploadNotice: unknown }).uploadNotice;
  if (typeof notice !== "object" || notice === null) return null;
  const { truncated, becameBase } = notice as Record<string, unknown>;
  return { truncated: truncated === true, becameBase: becameBase === true };
}
