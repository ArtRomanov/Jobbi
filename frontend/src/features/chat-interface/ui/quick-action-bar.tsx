import { useCallback } from "react";
import { colors, fonts } from "@/shared/ui";
import { QUICK_ACTIONS } from "../lib/constants";

interface QuickActionBarProps {
  onAction: (prompt: string) => void;
  hasCv: boolean;
  /** A message is being sent or streamed: every action waits for it. */
  disabled?: boolean;
  companyName: string;
  roleTitle: string;
}

function fillTemplate(
  template: string,
  companyName: string,
  roleTitle: string,
): string {
  return template
    .replace("{company_name}", companyName)
    .replace("{role_title}", roleTitle);
}

export function QuickActionBar({
  onAction,
  hasCv,
  disabled = false,
  companyName,
  roleTitle,
}: QuickActionBarProps) {
  const handleClick = useCallback(
    (template: string) => {
      onAction(fillTemplate(template, companyName, roleTitle));
    },
    [onAction, companyName, roleTitle],
  );

  return (
    <div
      style={{
        display: "flex",
        gap: "0.5rem",
        padding: "0.5rem 1rem",
        overflowX: "auto",
        flexShrink: 0,
      }}
    >
      {QUICK_ACTIONS.map((action) => {
        if (action.hiddenWithoutCv && !hasCv) return null;
        const isMissingCv = action.requiresCv && !hasCv;
        const isDisabled = disabled || isMissingCv;

        return (
          <button
            type="button"
            key={action.id}
            onClick={() => handleClick(action.template)}
            disabled={isDisabled}
            title={isMissingCv ? "Link a CV to this application first" : action.label}
            style={{
              padding: "0.375rem 0.875rem",
              border: `1px solid ${colors.primary}`,
              borderRadius: "999px",
              backgroundColor: isDisabled ? colors.bgDisabled : colors.bgCard,
              color: isDisabled ? colors.textMuted : colors.primary,
              fontSize: "0.8125rem",
              fontWeight: 500,
              fontFamily: fonts.base,
              cursor: isDisabled ? "not-allowed" : "pointer",
              whiteSpace: "nowrap",
              opacity: isDisabled ? 0.6 : 1,
              flexShrink: 0,
            }}
          >
            {action.label}
          </button>
        );
      })}
    </div>
  );
}
