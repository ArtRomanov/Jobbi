const SAFE_CV_LINK_PROTOCOLS: ReadonlySet<string> = new Set([
  "http:",
  "https:",
  "mailto:",
]);

// Whitespace and C0/DEL control characters. The URL parser silently strips
// some of them (e.g. "java\tscript:"), so a link carrying any is refused
// outright instead of trusting the parser's normalisation.
const UNSAFE_CHARS = /[\s\u0000-\u001f\u007f]/;

/**
 * True only for absolute http(s) and mailto URLs. Every link in the CV preview
 * and the CV PDF goes through this check: CV text is user input (and uploaded
 * files), so `javascript:`, `data:`, `vbscript:`, relative paths and the like
 * must never reach an `href`. Sibling of `isSafeExternalUrl`, plus `mailto:`.
 */
export function isSafeCvLinkUrl(url: string): boolean {
  if (url === "" || UNSAFE_CHARS.test(url)) return false;
  try {
    return SAFE_CV_LINK_PROTOCOLS.has(new URL(url).protocol);
  } catch {
    return false;
  }
}
