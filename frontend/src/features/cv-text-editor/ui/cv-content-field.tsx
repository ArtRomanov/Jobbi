import { useId, useLayoutEffect, useRef, type ClipboardEvent } from "react";
import { FormTextarea, colors } from "@/shared/ui";
import {
  CV_CONTENT_MAX_LENGTH,
  CV_CONTENT_PLACEHOLDER,
  CV_FORMATTING_HINT,
} from "../config";
import { insertTextWithinLimit } from "../lib/insert-text-within-limit";

interface CvContentFieldProps {
  value: string;
  onChange: (value: string) => void;
}

/**
 * The one textarea for the whole CV. `maxLength` stops typing at the limit.
 * A paste that would pass the limit is intercepted and cut to fit (browsers
 * differ on what they do there); any other paste stays native.
 */
export function CvContentField({ value, onChange }: CvContentFieldProps) {
  const hintId = useId();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pendingCaretRef = useRef<number | null>(null);

  // Put the caret after the pasted text once React has written the new value
  useLayoutEffect(() => {
    const caret = pendingCaretRef.current;
    if (caret === null || !textareaRef.current) return;
    pendingCaretRef.current = null;
    textareaRef.current.setSelectionRange(caret, caret);
  }, [value]);

  function handlePaste(event: ClipboardEvent<HTMLTextAreaElement>): void {
    const pasted = event.clipboardData.getData("text/plain");
    const { selectionStart, selectionEnd } = event.currentTarget;
    // A paste that fits stays native, so the browser's undo (Ctrl+Z) keeps it
    const lengthAfter = value.length - (selectionEnd - selectionStart) + pasted.length;
    if (lengthAfter <= CV_CONTENT_MAX_LENGTH) return;

    const next = insertTextWithinLimit(
      value,
      pasted,
      selectionStart,
      selectionEnd,
      CV_CONTENT_MAX_LENGTH,
    );
    event.preventDefault();
    if (next.value === value) return;
    pendingCaretRef.current = next.caret;
    onChange(next.value);
  }

  return (
    <div>
      <FormTextarea
        ref={textareaRef}
        label="CV text"
        rows={24}
        value={value}
        maxLength={CV_CONTENT_MAX_LENGTH}
        placeholder={CV_CONTENT_PLACEHOLDER}
        aria-describedby={hintId}
        spellCheck
        onChange={(event) => onChange(event.target.value)}
        onPaste={handlePaste}
      />
      <p
        id={hintId}
        style={{ margin: "-0.75rem 0 1rem", fontSize: "0.75rem", color: colors.textMuted }}
      >
        {CV_FORMATTING_HINT}
      </p>
    </div>
  );
}
