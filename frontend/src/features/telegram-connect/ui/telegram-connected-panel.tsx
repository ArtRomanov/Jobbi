import { useEffect, useRef, useState } from "react";
import { Button, colors } from "@/shared/ui";

interface TelegramConnectedPanelProps {
  username: string | null;
  isDisconnecting: boolean;
  onDisconnect: () => Promise<void>;
}

/** Connected state with an inline (non-modal) confirm step before disconnecting. */
export function TelegramConnectedPanel({
  username,
  isDisconnecting,
  onDisconnect,
}: TelegramConnectedPanelProps) {
  const [isConfirming, setIsConfirming] = useState(false);
  const disconnectRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const wasConfirmingRef = useRef(false);

  // Move focus into the confirm step, and back to "Disconnect" when it closes
  useEffect(() => {
    if (isConfirming) {
      cancelRef.current?.focus();
    } else if (wasConfirmingRef.current) {
      disconnectRef.current?.focus();
    }
    wasConfirmingRef.current = isConfirming;
  }, [isConfirming]);

  return (
    <div>
      <p style={{ fontSize: "0.875rem", color: colors.textSecondary, marginBottom: "1rem" }}>
        {username ? (
          <>
            Connected as <strong>@{username}</strong>
          </>
        ) : (
          <strong>Connected</strong>
        )}
      </p>

      {isConfirming ? (
        <div
          role="group"
          aria-label="Confirm disconnect"
          style={{
            padding: "0.75rem",
            border: `1px solid ${colors.border}`,
            borderRadius: "0.375rem",
          }}
        >
          <p style={{ fontSize: "0.875rem", color: colors.textSecondary, marginBottom: "0.75rem" }}>
            Disconnect Telegram? The bot will stop sending daily summaries and you won&apos;t be
            able to add applications from Telegram until you reconnect.
          </p>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <Button
              type="button"
              loading={isDisconnecting}
              onClick={() => void onDisconnect()}
              style={{ backgroundColor: colors.errorBg }}
            >
              Yes, disconnect
            </Button>
            <Button
              ref={cancelRef}
              type="button"
              variant="secondary"
              disabled={isDisconnecting}
              onClick={() => setIsConfirming(false)}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <Button
          ref={disconnectRef}
          type="button"
          variant="secondary"
          onClick={() => setIsConfirming(true)}
        >
          Disconnect
        </Button>
      )}
    </div>
  );
}
