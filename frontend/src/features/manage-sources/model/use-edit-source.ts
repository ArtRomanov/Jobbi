import { useCallback, useRef, useState } from "react";
import { getErrorMessage } from "@/shared/api";
import { updateVacancySource } from "@/entities/vacancy-source";
import type { VacancySource } from "@/entities/vacancy-source";
import type { EditSourceValues } from "./schemas";
import type { UseEditSourceResult } from "./types";

/**
 * Save for the Edit dialog: PATCHes the source, hands the server's copy to
 * `onSaved`; a failure becomes an inline error. A ref blocks double submits.
 */
export function useEditSource(
  sourceId: string,
  onSaved: (source: VacancySource) => void,
): UseEditSourceResult {
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isSavingRef = useRef(false);

  const save = useCallback(
    async (values: EditSourceValues): Promise<void> => {
      if (isSavingRef.current) return;
      isSavingRef.current = true;
      setIsSaving(true);
      setError(null);
      try {
        const updated = await updateVacancySource(sourceId, { name: values.name });
        isSavingRef.current = false;
        setIsSaving(false);
        onSaved(updated);
      } catch (caught: unknown) {
        isSavingRef.current = false;
        setIsSaving(false);
        setError(getErrorMessage(caught));
      }
    },
    [sourceId, onSaved],
  );

  return { isSaving, error, save };
}
