import { useRef, type KeyboardEvent } from "react";
import { colors } from "./theme";

export interface SegmentedControlOption<T extends string> {
  value: T;
  label: string;
}

interface SegmentedControlProps<T extends string> {
  /** Accessible name of the group (e.g. "Sort"). */
  label: string;
  options: readonly SegmentedControlOption<T>[];
  value: T;
  onChange: (value: T) => void;
}

const NEXT_KEYS = new Set(["ArrowRight", "ArrowDown"]);
const PREVIOUS_KEYS = new Set(["ArrowLeft", "ArrowUp"]);

/**
 * A row of mutually exclusive options with radio-group semantics.
 * Only the selected option is in the tab order; arrow keys (wrapping),
 * Home and End move both focus and selection, as native radios do.
 */
export function SegmentedControl<T extends string>({
  label,
  options,
  value,
  onChange,
}: SegmentedControlProps<T>) {
  const buttonsRef = useRef<(HTMLButtonElement | null)[]>([]);
  const selectedIndex = options.findIndex((option) => option.value === value);
  // With no match, the first option stays reachable by Tab
  const focusableIndex = selectedIndex === -1 ? 0 : selectedIndex;

  function select(index: number): void {
    const option = options[index];
    if (!option) return;
    buttonsRef.current[index]?.focus();
    if (option.value !== value) onChange(option.value);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number): void {
    const count = options.length;
    let target: number | null = null;
    if (NEXT_KEYS.has(event.key)) target = (index + 1) % count;
    else if (PREVIOUS_KEYS.has(event.key)) target = (index - 1 + count) % count;
    else if (event.key === "Home") target = 0;
    else if (event.key === "End") target = count - 1;
    if (target === null) return;
    event.preventDefault();
    select(target);
  }

  return (
    <div
      role="radiogroup"
      aria-label={label}
      style={{
        display: "inline-flex",
        padding: "0.125rem",
        gap: "0.125rem",
        border: `1px solid ${colors.border}`,
        borderRadius: "0.375rem",
        backgroundColor: colors.bgDisabled,
      }}
    >
      {options.map((option, index) => {
        const isSelected = index === selectedIndex;
        return (
          <button
            key={option.value}
            ref={(element) => {
              buttonsRef.current[index] = element;
            }}
            type="button"
            role="radio"
            aria-checked={isSelected}
            tabIndex={index === focusableIndex ? 0 : -1}
            onClick={() => select(index)}
            onKeyDown={(event) => handleKeyDown(event, index)}
            style={{
              padding: "0.25rem 0.75rem",
              border: "none",
              borderRadius: "0.25rem",
              fontSize: "0.875rem",
              fontWeight: isSelected ? 600 : 400,
              color: isSelected ? colors.primary : colors.textSecondary,
              backgroundColor: isSelected ? colors.bgCard : "transparent",
              boxShadow: isSelected ? "0 1px 2px rgba(0, 0, 0, 0.08)" : "none",
              cursor: "pointer",
            }}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
