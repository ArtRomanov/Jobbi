import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { getNewVacancyCount } from "../api/get-new-vacancy-count";
import { subscribeVacanciesChanged } from "./vacancies-changed";

/**
 * Count of new Inbox cards for the nav badge. Fetches on mount, on every route
 * change and on `notifyVacanciesChanged()`. Only the latest response wins; a
 * failed fetch keeps the previous count (0 before the first success).
 */
export function useNewVacancyCount(): number {
  const { pathname } = useLocation();
  const [count, setCount] = useState(0);
  const latestRequestRef = useRef(0);

  const refetch = useCallback(async (): Promise<void> => {
    latestRequestRef.current += 1;
    const requestId = latestRequestRef.current;
    try {
      const next = await getNewVacancyCount();
      if (requestId === latestRequestRef.current) setCount(next);
    } catch {
      // Keep the last known count; the next navigation or signal retries
    }
  }, []);

  useEffect(() => {
    void refetch();
  }, [pathname, refetch]);

  useEffect(
    () =>
      subscribeVacanciesChanged(() => {
        void refetch();
      }),
    [refetch],
  );

  useEffect(
    () => () => {
      // Drop responses that arrive after unmount
      latestRequestRef.current += 1;
    },
    [],
  );

  return count;
}
