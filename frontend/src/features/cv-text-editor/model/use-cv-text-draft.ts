import { useCallback, useState } from "react";
import { CV_NAME_REQUIRED_MESSAGE } from "../config";
import type { CvTextEditorValues } from "./types";

export interface CvTextDraft {
  name: string;
  content: string;
  nameError: string | null;
  setName: (name: string) => void;
  setContent: (content: string) => void;
  /** Shows "Required" and returns null for a blank name, else the values to save. */
  validate: () => CvTextEditorValues | null;
}

/**
 * The editor's unsaved name and text. Kept in one hook so dirty tracking and
 * the unsaved-changes guard (Slice 3) can compare it with the saved version.
 */
export function useCvTextDraft(initial: CvTextEditorValues): CvTextDraft {
  const [name, setNameState] = useState(initial.name);
  const [content, setContent] = useState(initial.content);
  const [nameError, setNameError] = useState<string | null>(null);

  const setName = useCallback((next: string) => {
    setNameState(next);
    // Clear the error as soon as the name is valid again
    if (next.trim()) setNameError(null);
  }, []);

  const validate = useCallback((): CvTextEditorValues | null => {
    const trimmed = name.trim();
    if (!trimmed) {
      setNameError(CV_NAME_REQUIRED_MESSAGE);
      return null;
    }
    return { name: trimmed, content };
  }, [name, content]);

  return { name, content, nameError, setName, setContent, validate };
}
