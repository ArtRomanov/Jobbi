/**
 * Open modals, innermost last. Only the top one reacts to Escape and pulls
 * focus back, so nested dialogs close one at a time.
 */
const openModals: object[] = [];

export function pushModal(token: object): void {
  openModals.push(token);
}

export function removeModal(token: object): void {
  const index = openModals.lastIndexOf(token);
  if (index !== -1) openModals.splice(index, 1);
}

export function isTopModal(token: object): boolean {
  return openModals[openModals.length - 1] === token;
}
