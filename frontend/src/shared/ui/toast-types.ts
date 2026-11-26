export type ToastType = "success" | "error" | "info";

/** A button inside the toast (e.g. "Undo"). Clicking it runs `onClick` and closes the toast. */
export interface ToastAction {
  label: string;
  onClick: () => void;
}

/** An in-app link inside the toast (e.g. "Open application"). Clicking it closes the toast. */
export interface ToastLink {
  label: string;
  to: string;
}

export interface ToastOptions {
  action?: ToastAction;
  link?: ToastLink;
  /** How long the toast stays, in ms. Defaults to 3000. */
  durationMs?: number;
  /**
   * Runs when the toast closes by its own timer (after any hover/focus pause),
   * not when its action / link is used or `dismissToast` closes it.
   */
  onTimeout?: () => void;
}

export interface ToastData {
  id: number;
  message: string;
  type: ToastType;
  action?: ToastAction;
  link?: ToastLink;
}

export interface ToastContextValue {
  /** Shows a toast; returns its id for `dismissToast`. */
  showToast: (message: string, type: ToastType, options?: ToastOptions) => number;
  /** Closes a toast early (no-op if it is already gone). */
  dismissToast: (id: number) => void;
}
