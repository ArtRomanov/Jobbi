import { useCallback, useState } from "react";
import { CV_NAME_REQUIRED_MESSAGE } from "../config";
import type { CvTextEditorValues } from "./types";

export interface CvTextDraft {
  name: string;
  content: string;
  nameError: string | null;
  /** The draft differs from `saved` (the name compared trimmed, as it is saved). */
  isDirty: boolean;
  setName: (name: string) => void;
  setContent: (content: string) => void;
  /** Shows "Required" and returns null for a blank name, else the values to save. */
  validate: () => CvTextEditorValues | null;
}

/**
 * The editor's unsaved name and text, and whether they differ from the last
 * saved version. `initial` is read once; `saved` follows every save.
 */
export function useCvTextDraft(
  initial: CvTextEditorValues,
  saved: CvTextEditorValues,
): CvTextDraft {
  const [name, setNameState] = useState(initial.name);
  const [content, setContent] = useState(initial.content);
  const [nameError, setNameError] = useState<string | null>(null);

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
    return { name: trimmed, content };
  }, [name, content]);

  const isDirty = name.trim() !== saved.name || content !== saved.content;

  return { name, content, nameError, isDirty, setName, setContent, validate };
}
