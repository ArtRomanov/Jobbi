import { useCallback, useState } from "react";
import { CV_NAME_REQUIRED_MESSAGE } from "../config";
import type { CvTextEditorValues } from "./types";

export interface CvTextDraft {
  name: string;
  content: string;
  isBase: boolean;
  nameError: string | null;
  /**
   * The draft differs from `saved` (the name compared trimmed, as it is
   * saved), or the "Base CV" switch does.
   */
  isDirty: boolean;
  setName: (name: string) => void;
  setContent: (content: string) => void;
  setIsBase: (isBase: boolean) => void;
  /** Shows "Required" and returns null for a blank name, else the values to save. */
  validate: () => CvTextEditorValues | null;
}

/**
 * The editor's unsaved name, text and "Base CV" switch, and whether they
 * differ from the last saved version. `initial` is read once; `saved`
 * follows every save.
 */
export function useCvTextDraft(
  initial: CvTextEditorValues,
  saved: CvTextEditorValues,
): CvTextDraft {
  const [name, setNameState] = useState(initial.name);
  const [content, setContent] = useState(initial.content);
  const [isBase, setIsBase] = useState(initial.isBase);
  const [nameError, setNameError] = useState<string | null>(null);

  // After every save the switch follows the server's answer: the base may have
  // changed elsewhere, and a stale switch would leave Save and the guard dirty.
  // Name and text are not re-seeded, so typing is never overwritten. Adjusted
  // during render (React's "store previous prop" pattern), not in an effect,
  // so no frame shows a dirty Save.
  const [syncedSaved, setSyncedSaved] = useState(saved);
  if (saved !== syncedSaved) {
    setSyncedSaved(saved);
    setIsBase(saved.isBase);
  }

  const setName = useCallback((next: string) => {
    setNameState(next);
    // A blank name shows "Required" while typing; a valid one clears it
    setNameError(next.trim() ? null : CV_NAME_REQUIRED_MESSAGE);
  }, []);

  const validate = useCallback((): CvTextEditorValues | null => {
    const trimmed = name.trim();
    if (!trimmed) {
      setNameError(CV_NAME_REQUIRED_MESSAGE);
      return null;
    }
    return { name: trimmed, content, isBase };
  }, [name, content, isBase]);

  const isDirty =
    name.trim() !== saved.name || content !== saved.content || isBase !== saved.isBase;

  return {
    name,
    content,
    isBase,
    nameError,
    isDirty,
    setName,
    setContent,
    setIsBase,
    validate,
  };
}
