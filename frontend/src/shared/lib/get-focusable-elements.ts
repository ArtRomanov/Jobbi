const NOT_SKIPPED = ":not([disabled]):not([tabindex='-1'])";

/** Form fields a dialog focuses first. */
export const FIELD_SELECTOR = [
  `input${NOT_SKIPPED}:not([type='hidden'])`,
  `select${NOT_SKIPPED}`,
  `textarea${NOT_SKIPPED}`,
].join(",");

const FOCUSABLE_SELECTOR = [
  `a[href]:not([tabindex='-1'])`,
  `button${NOT_SKIPPED}`,
  FIELD_SELECTOR,
  "[tabindex]:not([tabindex='-1'])",
].join(",");

/** Inside `[hidden]`, `[inert]` or `[aria-hidden="true"]` (itself or an ancestor). */
function isHidden(element: HTMLElement): boolean {
  return element.closest("[hidden], [inert], [aria-hidden='true']") !== null;
}

/** Elements inside `container` that Tab can reach, in DOM order. */
export function getFocusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (element) => !isHidden(element),
  );
}

/** First visible form field in `container`, or null. */
export function getFirstField(container: HTMLElement): HTMLElement | null {
  return (
    Array.from(container.querySelectorAll<HTMLElement>(FIELD_SELECTOR)).find(
      (element) => !isHidden(element),
    ) ?? null
  );
}
