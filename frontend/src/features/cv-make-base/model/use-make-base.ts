import { useCallback, useRef, useState } from "react";
import { makeBaseCv, type Cv } from "@/entities/cv";
import { handleApiError } from "@/shared/api";
import { useToast } from "@/shared/ui";
import { BASE_UPDATED_MESSAGE } from "../lib/constants";

export interface UseMakeBaseResult {
  isPending: boolean;
  makeBase: () => Promise<void>;
}

/**
 * "Make base" for one CV: POST make-base, toast "Base CV updated", then
 * `onMadeBase` so the owner refreshes its list. A ref drops double clicks.
 */
export function useMakeBase(cvId: string, onMadeBase: (cv: Cv) => void): UseMakeBaseResult {
  const [isPending, setIsPending] = useState(false);
  const isPendingRef = useRef(false);
  const { showToast } = useToast();

  const makeBase = useCallback(async (): Promise<void> => {
    if (isPendingRef.current) return;
    isPendingRef.current = true;
    setIsPending(true);
    try {
      const updated = await makeBaseCv(cvId);
      showToast(BASE_UPDATED_MESSAGE, "success");
      onMadeBase(updated);
    } catch (err: unknown) {
      handleApiError(err, showToast);
    } finally {
      isPendingRef.current = false;
      setIsPending(false);
    }
  }, [cvId, onMadeBase, showToast]);

  return { isPending, makeBase };
}
