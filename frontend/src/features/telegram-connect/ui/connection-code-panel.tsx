import { Button, colors } from "@/shared/ui";
import { BOT_DISPLAY_NAME } from "../lib/constants";
import { formatClockTime } from "../lib/helpers";

interface ConnectionCodePanelProps {
  code: string;
  expiresAtMs: number;
  onCancel: () => void;
}

/** Shows the one-time code plus linking instructions while polling runs. */
export function ConnectionCodePanel({ code, expiresAtMs, onCancel }: ConnectionCodePanelProps) {
  return (
    <div>
      <p style={{ fontSize: "0.875rem", color: colors.textSecondary, marginBottom: "0.75rem" }}>
        Open {BOT_DISPLAY_NAME} in Telegram, send <code>/start</code>, then send the code:
      </p>
      <p
        style={{
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          fontSize: "1.75rem",
          fontWeight: 700,
          letterSpacing: "0.3em",
          textAlign: "center",
          padding: "0.75rem",
          marginBottom: "0.75rem",
          border: `1px dashed ${colors.border}`,
          borderRadius: "0.375rem",
          backgroundColor: colors.bgDisabled,
          color: colors.textPrimary,
        }}
      >
        {code}
      </p>
      <p style={{ fontSize: "0.75rem", color: colors.textMuted, marginBottom: "1rem" }}>
        Code expires at {formatClockTime(expiresAtMs)}. Waiting for you to send it — this
        section updates automatically once you&apos;re connected.
      </p>
      <Button type="button" variant="secondary" onClick={onCancel}>
        Cancel
      </Button>
    </div>
  );
}
