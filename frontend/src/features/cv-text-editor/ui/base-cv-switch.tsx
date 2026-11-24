import { useId } from "react";
import { colors } from "@/shared/ui";
import { BASE_CV_SWITCH_HELP, BASE_CV_SWITCH_LABEL } from "../config";

interface BaseCvSwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
}

/**
 * The "Base CV" switch (spec 011 §2.1). A native checkbox with
 * `role="switch"`, so Space toggles it and screen readers say "on/off";
 * the change is part of the unsaved draft and takes effect on Save.
 */
export function BaseCvSwitch({ checked, onChange }: BaseCvSwitchProps) {
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
          cursor: "pointer",
        }}
      >
        <input
          type="checkbox"
          role="switch"
          checked={checked}
          aria-describedby={helpId}
          onChange={(event) => onChange(event.target.checked)}
          style={{ width: "1rem", height: "1rem", margin: 0, accentColor: colors.primary }}
        />
        {BASE_CV_SWITCH_LABEL}
      </label>
      <p id={helpId} style={{ margin: "0.25rem 0 0", fontSize: "0.75rem", color: colors.textMuted }}>
        {BASE_CV_SWITCH_HELP}
      </p>
    </div>
  );
}
