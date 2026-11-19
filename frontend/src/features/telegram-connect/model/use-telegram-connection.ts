import { useCallback, useEffect, useState } from "react";
import { handleApiError } from "@/shared/api";
import { useToast } from "@/shared/ui";
import {
  disconnectTelegram,
  generateConnectionCode,
  getTelegramStatus,
} from "@/entities/telegram";
import type { TelegramStatus } from "@/entities/telegram";
import { STATUS_POLL_INTERVAL_MS } from "../lib/constants";
import { getExpiryDelayMs, parseUtcDate, statusToState } from "../lib/helpers";
import type {
  TelegramConnectionState,
  UseTelegramConnectionResult,
} from "./types";

/**
 * Owns the Telegram link lifecycle: initial status load, code generation,
 * status polling while a code is displayed, and disconnect.
 *
 * Polling runs only in the "awaiting-link" state and stops when the link is
 * detected, the code expires, the code is cancelled, or the component unmounts.
 * On expiry one final status check runs, so a link made in the last seconds
 * is not misreported as "expired".
 */
export function useTelegramConnection(): UseTelegramConnectionResult {
  const { showToast } = useToast();
  const [state, setState] = useState<TelegramConnectionState>({ status: "loading" });
  const [reloadKey, setReloadKey] = useState(0);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);

  // Initial (and retry) status load
  useEffect(() => {
    let cancelled = false;

    async function load(): Promise<void> {
      try {
        const status = await getTelegramStatus();
        if (!cancelled) setState(statusToState(status));
      } catch {
        if (!cancelled) setState({ status: "load-error" });
      }
    }

    void load();
    return () => { cancelled = true; };
  }, [reloadKey]);

  // Primitive deps so the effect restarts only when a new code is issued
  const pendingCode = state.status === "awaiting-link" ? state.code : null;
  const expiresAtMs = state.status === "awaiting-link" ? state.expiresAtMs : null;

  // Poll status while a code is on screen; stop on link, expiry, or unmount
  useEffect(() => {
    if (pendingCode === null || expiresAtMs === null) return;

    // `cancelled`: effect cleaned up (ignore everything). `isStopped`: polling
    // halted because the code expired (only the final check may settle state).
    let cancelled = false;
    let isStopped = false;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;

    function markConnected(status: TelegramStatus): void {
      setState(statusToState(status));
      showToast("Telegram connected.", "success");
    }

    async function finalCheck(): Promise<void> {
      isStopped = true;
      clearTimeout(pollTimer);
      try {
        const status = await getTelegramStatus();
        if (cancelled) return;
        if (status.connected) {
          markConnected(status);
          return;
        }
      } catch {
        if (cancelled) return;
      }
      setState({ status: "not-connected", isCodeExpired: true });
    }

    const expiryTimer = setTimeout(
      () => void finalCheck(),
      getExpiryDelayMs(expiresAtMs, Date.now()),
    );

    // Chained timeouts (not setInterval) so slow responses never overlap
    async function poll(): Promise<void> {
      try {
        const status = await getTelegramStatus();
        if (cancelled || isStopped) return;
        if (status.connected) {
          markConnected(status);
          return;
        }
      } catch {
        // Transient failure: keep polling until the code expires
      }
      if (!cancelled && !isStopped) pollTimer = setTimeout(() => void poll(), STATUS_POLL_INTERVAL_MS);
    }

    pollTimer = setTimeout(() => void poll(), STATUS_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearTimeout(pollTimer);
      clearTimeout(expiryTimer);
    };
  }, [pendingCode, expiresAtMs, showToast]);

  const connect = useCallback(async (): Promise<void> => {
    if (isGenerating) return;
    setIsGenerating(true);
    try {
      const result = await generateConnectionCode();
      const parsedExpiresAtMs = parseUtcDate(result.expires_at).getTime();
      if (Number.isNaN(parsedExpiresAtMs)) {
        showToast("Something went wrong. Please try again.", "error");
        return;
      }
      setState({ status: "awaiting-link", code: result.code, expiresAtMs: parsedExpiresAtMs });
    } catch (error: unknown) {
      handleApiError(error, showToast);
    } finally {
      setIsGenerating(false);
    }
  }, [isGenerating, showToast]);

  const cancelCode = useCallback((): void => {
    setState({ status: "not-connected", isCodeExpired: false });
  }, []);

  const disconnect = useCallback(async (): Promise<void> => {
    setIsDisconnecting(true);
    try {
      await disconnectTelegram();
      setState({ status: "not-connected", isCodeExpired: false });
      showToast("Telegram disconnected.", "success");
    } catch (error: unknown) {
      handleApiError(error, showToast);
    } finally {
      setIsDisconnecting(false);
    }
  }, [showToast]);

  const retry = useCallback((): void => {
    setState({ status: "loading" });
    setReloadKey((key) => key + 1);
  }, []);

  return { state, isGenerating, isDisconnecting, connect, cancelCode, disconnect, retry };
}
