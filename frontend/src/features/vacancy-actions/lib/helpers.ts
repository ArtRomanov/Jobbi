const SAFE_PROTOCOLS = new Set(["http:", "https:"]);

/**
 * True only for absolute http(s) URLs. Source URLs come from scraped posts,
 * so `javascript:`, `data:` and the like must never reach `window.open`.
 */
export function isSafeExternalUrl(url: string): boolean {
  try {
    return SAFE_PROTOCOLS.has(new URL(url).protocol);
  } catch {
    return false;
  }
}
