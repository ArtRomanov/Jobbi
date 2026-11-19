import { useEffect, useId, useRef, type ReactNode } from "react";
import { Button, SectionHeader, colors } from "@/shared/ui";
import { useTelegramConnection } from "../model/use-telegram-connection";
import { MUTED_TEXT_STYLE } from "../lib/constants";
import { getStatusLabel } from "../lib/helpers";
import { ConnectionCodePanel } from "./connection-code-panel";
import { TelegramConnectedPanel } from "./telegram-connected-panel";

/** Settings section for linking / unlinking the user's Telegram account. */
export function TelegramSection() {
  const headingId = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const sectionRef = useRef<HTMLElement>(null);
  const prevStatusRef = useRef<string | null>(null);
  const isUserActionRef = useRef(false);
  const { state, isGenerating, isDisconnecting, connect, cancelCode, disconnect, retry } =
    useTelegramConnection();

  // When the panel swaps, its focused button unmounts and focus falls to <body>.
  // Move focus to the heading after user-initiated changes, or when focus was
  // inside the section / lost — but never on the initial status load.
  useEffect(() => {
    const prevStatus = prevStatusRef.current;
    prevStatusRef.current = state.status;
    if (prevStatus === null || prevStatus === state.status) return;

    const active = document.activeElement;
    const isFocusLost =
      active === null ||
      active === document.body ||
      (sectionRef.current?.contains(active) ?? false);
    const isInitialLoad = prevStatus === "loading" && !isUserActionRef.current;

    if (!isInitialLoad && (isUserActionRef.current || isFocusLost)) {
      headingRef.current?.focus();
    }
    if (state.status !== "loading") isUserActionRef.current = false;
  }, [state.status]);

  const markUserAction = (): void => {
    isUserActionRef.current = true;
  };

  let content: ReactNode;
  switch (state.status) {
    case "loading":
      content = null;
      break;
    case "load-error":
      content = (
        <Button
          type="button"
          variant="secondary"
          onClick={() => {
            markUserAction();
            retry();
          }}
        >
          Try again
        </Button>
      );
      break;
    case "not-connected":
      content = (
        <>
          {state.isCodeExpired ? (
            <p style={{ ...MUTED_TEXT_STYLE, marginBottom: "0.75rem" }}>
              Generate a new code to try again.
            </p>
          ) : null}
          <Button
            type="button"
            loading={isGenerating}
            onClick={() => {
              markUserAction();
              void connect();
            }}
          >
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
          onCancel={() => {
            markUserAction();
            cancelCode();
          }}
        />
      );
      break;
    case "connected":
      content = (
        <TelegramConnectedPanel
          isDisconnecting={isDisconnecting}
          onDisconnect={async () => {
            markUserAction();
            await disconnect();
          }}
        />
      );
      break;
  }

  const isError = state.status === "load-error";

  return (
    <section ref={sectionRef} aria-labelledby={headingId}>
      <SectionHeader
        id={headingId}
        headingRef={headingRef}
        title="Telegram"
        subtitle="Add applications from Telegram and get a daily pipeline summary"
      />
      <p aria-live="polite" style={{ ...MUTED_TEXT_STYLE, marginBottom: "0.75rem" }}>
        Status:{" "}
        <strong style={{ color: isError ? colors.error : colors.textSecondary }}>
          {getStatusLabel(state)}
        </strong>
      </p>
      {content}
    </section>
  );
}
