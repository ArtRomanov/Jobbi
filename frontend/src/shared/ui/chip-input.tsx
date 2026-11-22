import {
  useEffect,
  useId,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent,
} from "react";
import { appendUniqueTerms } from "@/shared/lib";
import { colors } from "./theme";

interface ChipInputProps {
  label: string;
  /** Current chips (controlled). */
  values: readonly string[];
  onChange: (values: readonly string[]) => void;
  /** When the list holds this many chips, the input is disabled and `maxItemsMessage` shown. */
  maxItems?: number;
  maxItemsMessage?: string;
  /** Max characters per chip; longer input is cut. */
  maxLength?: number;
  placeholder?: string;
  /** Short help text under the input (linked via aria-describedby). */
  hint?: string;
  disabled?: boolean;
  id?: string;
}

/** Where focus goes after the next `values` change (set by the action that caused it). */
type PendingFocus = "input" | "last-chip" | null;

const SEPARATOR = ",";

/**
 * Controlled list of string chips with a text input. Enter or a comma adds the
 * typed term (trimmed; empty and case-insensitive duplicates are ignored); the
 * term is also added when the input loses focus. Backspace on an empty input
 * removes the last chip. Each chip has a "Remove <term>" button.
 */
export function ChipInput({
  label,
  values,
  onChange,
  maxItems,
  maxItemsMessage,
  maxLength,
  placeholder,
  hint,
  disabled = false,
  id: providedId,
}: ChipInputProps) {
  const generatedId = useId();
  const id = providedId ?? generatedId;
  const hintId = `${id}-hint`;
  const limitId = `${id}-limit`;
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const pendingFocusRef = useRef<PendingFocus>(null);

  const isFull = maxItems !== undefined && values.length >= maxItems;
  const isInputDisabled = disabled || isFull;
  const describedBy =
    [hint ? hintId : null, isFull && maxItemsMessage ? limitId : null]
      .filter((value): value is string => value !== null)
      .join(" ") || undefined;

  // Runs after the chips re-render, so a just-enabled input or a new last chip exists
  useEffect(() => {
    const target = pendingFocusRef.current;
    pendingFocusRef.current = null;
    if (target === "input") {
      inputRef.current?.focus();
    } else if (target === "last-chip") {
      const buttons = listRef.current?.querySelectorAll("button");
      buttons?.[buttons.length - 1]?.focus();
    }
  }, [values]);

  const commit = (rawTerms: readonly string[]): void => {
    const next = appendUniqueTerms(values, rawTerms, { maxItems, maxLength });
    if (next === values) return;
    // Reaching the limit disables the focused input; keep focus inside the control
    if (maxItems !== undefined && next.length >= maxItems && document.activeElement === inputRef.current) {
      pendingFocusRef.current = "last-chip";
    }
    onChange(next);
  };

  const handleChange = (event: ChangeEvent<HTMLInputElement>): void => {
    const parts = event.target.value.split(SEPARATOR);
    const rest = parts.pop() ?? "";
    if (parts.length > 0) commit(parts);
    setDraft(maxLength === undefined ? rest : rest.slice(0, maxLength));
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>): void => {
    if (event.key === "Enter") {
      // Never submit a surrounding form from here
      event.preventDefault();
      commit([draft]);
      setDraft("");
    } else if (event.key === "Backspace" && draft === "" && values.length > 0) {
      event.preventDefault();
      onChange(values.slice(0, -1));
    }
  };

  const handleBlur = (): void => {
    if (draft.trim() === "") return;
    commit([draft]);
    setDraft("");
  };

  const handleRemove = (term: string): void => {
    pendingFocusRef.current = "input";
    onChange(values.filter((value) => value !== term));
  };

  return (
    <div style={{ marginBottom: "1rem" }}>
      <label
        htmlFor={id}
        style={{
          display: "block",
          marginBottom: "0.25rem",
          fontSize: "0.875rem",
          fontWeight: 500,
          color: colors.textSecondary,
        }}
      >
        {label}
      </label>
      {values.length > 0 ? (
        <ul
          ref={listRef}
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "0.375rem",
            listStyle: "none",
            margin: "0 0 0.5rem",
            padding: 0,
          }}
        >
          {values.map((term) => (
            <li
              key={term}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.25rem",
                padding: "0.125rem 0.25rem 0.125rem 0.625rem",
                borderRadius: "999px",
                backgroundColor: colors.bgDisabled,
                border: `1px solid ${colors.borderLight}`,
                fontSize: "0.8125rem",
                color: colors.textPrimary,
                maxWidth: "100%",
              }}
            >
              <span style={{ overflowWrap: "anywhere" }}>{term}</span>
              <button
                type="button"
                aria-label={`Remove ${term}`}
                disabled={disabled}
                onClick={() => handleRemove(term)}
                style={{
                  border: "none",
                  background: "transparent",
                  color: colors.textMuted,
                  cursor: disabled ? "not-allowed" : "pointer",
                  fontSize: "1rem",
                  lineHeight: 1,
                  padding: "0 0.25rem",
                  borderRadius: "999px",
                }}
              >
                <span aria-hidden="true">×</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <input
        ref={inputRef}
        id={id}
        type="text"
        value={draft}
        placeholder={placeholder}
        disabled={isInputDisabled}
        autoComplete="off"
        aria-describedby={describedBy}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onBlur={handleBlur}
        style={{
          width: "100%",
          padding: "0.5rem 0.75rem",
          border: `1px solid ${colors.border}`,
          borderRadius: "0.375rem",
          fontSize: "0.875rem",
          outline: "none",
          boxSizing: "border-box",
        }}
      />
      {hint ? (
        <p id={hintId} style={{ marginTop: "0.25rem", fontSize: "0.75rem", color: colors.textMuted }}>
          {hint}
        </p>
      ) : null}
      {isFull && maxItemsMessage ? (
        <p
          id={limitId}
          role="status"
          style={{ marginTop: "0.25rem", fontSize: "0.75rem", color: colors.textSecondary }}
        >
          {maxItemsMessage}
        </p>
      ) : null}
    </div>
  );
}
