const SAFE_PROTOCOLS: ReadonlySet<string> = new Set(["http:", "https:"]);

/**
 * True only for absolute http(s) URLs. Job/source URLs come from users and
 * scraped posts, so `javascript:`, `data:`, relative paths and the like must
 * never reach an `href` or `window.open`.
 */
export function isSafeExternalUrl(url: string): boolean {
  try {
    return SAFE_PROTOCOLS.has(new URL(url).protocol);
  } catch {
    return false;
  }
}
