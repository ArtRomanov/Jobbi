import { useId, useLayoutEffect, useRef, type ClipboardEvent } from "react";
import { FormTextarea, VisuallyHidden, colors } from "@/shared/ui";
import {
  CV_CONTENT_COUNTER_THRESHOLD,
  CV_CONTENT_MAX_LENGTH,
  CV_CONTENT_PLACEHOLDER,
  CV_FORMATTING_HINT,
  CV_FORMATTING_HINT_DESCRIPTION,
  CV_PANE_BOX_STYLE,
} from "../config";
import { formatThousands } from "../lib/format-thousands";
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
  const counterId = useId();
  const showCounter = value.length > CV_CONTENT_COUNTER_THRESHOLD;
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
        value={value}
        // Same box as the preview; a fixed height, so no resize handle
        style={{ ...CV_PANE_BOX_STYLE, resize: "none" }}
        maxLength={CV_CONTENT_MAX_LENGTH}
        placeholder={CV_CONTENT_PLACEHOLDER}
        aria-describedby={showCounter ? `${hintId} ${counterId}` : hintId}
        spellCheck
        onChange={(event) => onChange(event.target.value)}
        onPaste={handlePaste}
      />
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: "0.75rem",
          margin: "-0.75rem 0 1rem",
          fontSize: "0.75rem",
          color: colors.textMuted,
        }}
      >
        <p style={{ margin: 0 }}>
          {/* Symbols for the eye; plain words for screen readers */}
          <span aria-hidden="true">{CV_FORMATTING_HINT}</span>
          <span id={hintId}>
            <VisuallyHidden>{CV_FORMATTING_HINT_DESCRIPTION}</VisuallyHidden>
          </span>
        </p>
        {showCounter ? (
          <p id={counterId} style={{ margin: 0, whiteSpace: "nowrap" }}>
            {`${formatThousands(value.length)} / ${formatThousands(CV_CONTENT_MAX_LENGTH)}`}
          </p>
        ) : null}
      </div>
    </div>
  );
}
