/** UI state machine for the Telegram link section. */
export type TelegramConnectionState =
  | { status: "loading" }
  | { status: "load-error" }
  | { status: "not-connected"; isCodeExpired: boolean }
  /** `expiresAtMs`: client-clock time the UI expires the code (receipt + TTL). */
  | { status: "awaiting-link"; code: string; expiresAtMs: number }
  | { status: "connected"; username: string | null };

export interface UseTelegramConnectionResult {
  state: TelegramConnectionState;
  isGenerating: boolean;
  isDisconnecting: boolean;
  connect: () => Promise<void>;
  cancelCode: () => void;
  disconnect: () => Promise<void>;
  retry: () => void;
}
