import { useEffect, useState } from "react";

/**
 * Debounce a value — returns the latest value only after `delay` ms of
 * inactivity. Useful for search inputs where you don't want to fire a
 * request on every keystroke.
 */
export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(timer);
    };
  }, [value, delay]);

  return debouncedValue;
}
