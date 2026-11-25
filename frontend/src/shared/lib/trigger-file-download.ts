// Some browsers start reading the blob only after click() returns; revoking
// the object URL right away can cancel the download.
const REVOKE_DELAY_MS = 1000;

/** Saves a blob in the browser under `fileName` (CV PDF and HTML exports). */
export function triggerFileDownload(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(url), REVOKE_DELAY_MS);
}
