import { useId } from "react";
import { colors } from "@/shared/ui";
import { KEYWORD_FILTER_HELP, KEYWORD_FILTER_LABEL } from "../lib/constants";

interface KeywordFilterSwitchProps {
  checked: boolean;
  disabled: boolean;
  onChange: (checked: boolean) => void;
}

/**
 * "Only send posts with these words to the AI" (`keyword_filter`). A native
 * checkbox with `role="switch"`, so Space toggles it and screen readers say
 * "on/off"; part of the draft, applied on Save. The help text is linked via
 * `aria-describedby`.
 */
export function KeywordFilterSwitch({ checked, disabled, onChange }: KeywordFilterSwitchProps) {
  const helpId = useId();

  return (
    <div style={{ margin: "0 0 1rem" }}>
      <label
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "0.5rem",
          fontSize: "0.875rem",
          fontWeight: 500,
          color: colors.textPrimary,
          cursor: disabled ? "not-allowed" : "pointer",
        }}
      >
        <input
          type="checkbox"
          role="switch"
          checked={checked}
          disabled={disabled}
          aria-describedby={helpId}
          onChange={(event) => onChange(event.target.checked)}
          style={{ width: "1rem", height: "1rem", margin: 0, accentColor: colors.primary }}
        />
        {KEYWORD_FILTER_LABEL}
      </label>
      <p id={helpId} style={{ margin: "0.25rem 0 0", fontSize: "0.75rem", color: colors.textMuted }}>
        {KEYWORD_FILTER_HELP}
      </p>
    </div>
  );
}
