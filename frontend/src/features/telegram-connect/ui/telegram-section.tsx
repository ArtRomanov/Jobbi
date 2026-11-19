import { useId, type ReactNode } from "react";
import { Button, SectionHeader, colors } from "@/shared/ui";
import { useTelegramConnection } from "../model/use-telegram-connection";
import { ConnectionCodePanel } from "./connection-code-panel";
import { TelegramConnectedPanel } from "./telegram-connected-panel";

const mutedText = { fontSize: "0.875rem", color: colors.textMuted } as const;

/** Settings section for linking / unlinking the user's Telegram account. */
export function TelegramSection() {
  const headingId = useId();
  const { state, isGenerating, isDisconnecting, connect, cancelCode, disconnect, retry } =
    useTelegramConnection();

  let content: ReactNode;
  switch (state.status) {
    case "loading":
      content = <p style={mutedText}>Checking Telegram status...</p>;
      break;
    case "load-error":
      content = (
        <>
          <p role="alert" style={{ ...mutedText, color: colors.error, marginBottom: "0.75rem" }}>
            Could not load Telegram status.
          </p>
          <Button type="button" variant="secondary" onClick={retry}>
            Try again
          </Button>
        </>
      );
      break;
    case "not-connected":
      content = (
        <>
          <p style={{ ...mutedText, marginBottom: "0.75rem" }}>
            Status: <strong style={{ color: colors.textSecondary }}>Not connected</strong>
          </p>
          {state.isCodeExpired ? (
            <p style={{ ...mutedText, color: colors.error, marginBottom: "0.75rem" }}>
              That code expired. Generate a new one to try again.
            </p>
          ) : null}
          <Button type="button" loading={isGenerating} onClick={() => void connect()}>
            {state.isCodeExpired ? "Generate new code" : "Connect Telegram"}
          </Button>
        </>
      );
      break;
    case "awaiting-link":
      content = (
        <ConnectionCodePanel
          code={state.code}
          expiresAtMs={state.expiresAtMs}
          onCancel={cancelCode}
        />
      );
      break;
    case "connected":
      content = (
        <TelegramConnectedPanel
          username={state.username}
          isDisconnecting={isDisconnecting}
          onDisconnect={disconnect}
        />
      );
      break;
  }

  return (
    <section aria-labelledby={headingId}>
      <SectionHeader
        id={headingId}
        title="Telegram"
        subtitle="Add applications from Telegram and get a daily pipeline summary"
      />
      <div aria-live="polite">{content}</div>
    </section>
  );
}
