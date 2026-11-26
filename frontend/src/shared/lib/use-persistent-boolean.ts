import { useCallback, useState } from "react";

/** Stored value under `key`, or `fallback` when absent, unreadable or not "true"/"false". */
function readStoredBoolean(key: string, fallback: boolean): boolean {
  try {
    const stored = window.localStorage.getItem(key);
    if (stored === "true") return true;
    if (stored === "false") return false;
  } catch {
    // Private mode / blocked storage: use the default
  }
  return fallback;
}

function writeStoredBoolean(key: string, value: boolean): void {
  try {
    window.localStorage.setItem(key, String(value));
  } catch {
    // Blocked or full storage: the choice lasts for this page only
  }
}

interface PersistentBooleanOptions {
  /** Start with this value on this mount instead of the stored one (it is not saved). */
  initialValue?: boolean;
}

/**
 * Boolean state remembered per browser in localStorage under `key`. Only the
 * setter writes, so a mount never saves anything; storage errors are ignored.
 */
export function usePersistentBoolean(
  key: string,
  defaultValue: boolean,
  { initialValue }: PersistentBooleanOptions = {},
): [boolean, (next: boolean) => void] {
  const [value, setValue] = useState(() => initialValue ?? readStoredBoolean(key, defaultValue));

  const setAndStore = useCallback(
    (next: boolean): void => {
      setValue(next);
      writeStoredBoolean(key, next);
    },
    [key],
  );

  return [value, setAndStore];
}
