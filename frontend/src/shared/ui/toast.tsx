import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ToastItem } from "./toast-item";
import type { ToastContextValue, ToastData, ToastOptions, ToastType } from "./toast-types";

const DEFAULT_TOAST_DURATION_MS = 3000;

const ToastContext = createContext<ToastContextValue | null>(null);

let nextId = 0;

interface ToastTimer {
  /** null while paused */
  timer: ReturnType<typeof setTimeout> | null;
  endsAt: number;
  remainingMs: number;
}

const REGION_STYLE = { display: "flex", flexDirection: "column", gap: "0.5rem" } as const;

/**
 * Renders toasts in live regions: errors in a `role="alert"` region, the rest
 * in a polite one, with any action button ("Undo") or link inside the region.
 * A toast's timer pauses while it is hovered or focused (WCAG 2.2.1), so a
 * keyboard or screen-reader user can still reach its action.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastData[]>([]);
  const timersRef = useRef<Map<number, ToastTimer>>(new Map());
  // `onTimeout` per toast; dropped when the toast closes any other way
  const timeoutHandlersRef = useRef<Map<number, () => void>>(new Map());

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach(({ timer }) => {
        if (timer !== null) clearTimeout(timer);
      });
    };
  }, []);

  const dismissToast = useCallback((id: number): void => {
    const entry = timersRef.current.get(id);
    if (entry?.timer) clearTimeout(entry.timer);
    timersRef.current.delete(id);
    timeoutHandlersRef.current.delete(id);
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const expireToast = useCallback(
    (id: number): void => {
      const onTimeout = timeoutHandlersRef.current.get(id);
      dismissToast(id);
      onTimeout?.();
    },
    [dismissToast],
  );

  const startTimer = useCallback(
    (id: number, durationMs: number): void => {
      timersRef.current.set(id, {
        timer: setTimeout(() => expireToast(id), durationMs),
        endsAt: Date.now() + durationMs,
        remainingMs: durationMs,
      });
    },
    [expireToast],
  );

  const pauseToast = useCallback((id: number): void => {
    const entry = timersRef.current.get(id);
    if (!entry || entry.timer === null) return;
    clearTimeout(entry.timer);
    entry.timer = null;
    entry.remainingMs = Math.max(0, entry.endsAt - Date.now());
  }, []);

  const resumeToast = useCallback(
    (id: number): void => {
      const entry = timersRef.current.get(id);
      if (!entry || entry.timer !== null) return;
      startTimer(id, entry.remainingMs);
    },
    [startTimer],
  );

  const showToast = useCallback(
    (message: string, type: ToastType, options: ToastOptions = {}): number => {
      const id = nextId++;
      const { action, link, durationMs = DEFAULT_TOAST_DURATION_MS, onTimeout } = options;
      if (onTimeout) timeoutHandlersRef.current.set(id, onTimeout);
      setToasts((prev) => [...prev, { id, message, type, action, link }]);
      startTimer(id, durationMs);
      return id;
    },
    [startTimer],
  );

  const errorToasts = toasts.filter((toast) => toast.type === "error");
  const politeToasts = toasts.filter((toast) => toast.type !== "error");

  const value = useMemo(() => ({ showToast, dismissToast }), [showToast, dismissToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        style={{
          position: "fixed",
          top: "1rem",
          right: "1rem",
          zIndex: 9999,
          ...REGION_STYLE,
        }}
      >
        <div aria-live="polite" style={REGION_STYLE}>
          {politeToasts.map((toast) => (
            <ToastItem
              key={toast.id}
              toast={toast}
              onClose={dismissToast}
              onPause={pauseToast}
              onResume={resumeToast}
            />
          ))}
        </div>
        {/* Only while errors show, so it never adds an empty "alert" to the page */}
        {errorToasts.length > 0 ? (
          <div role="alert" style={REGION_STYLE}>
            {errorToasts.map((toast) => (
              <ToastItem
                key={toast.id}
                toast={toast}
                onClose={dismissToast}
                onPause={pauseToast}
                onResume={resumeToast}
              />
            ))}
          </div>
        ) : null}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}
