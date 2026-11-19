import { useCallback, useEffect, useState } from "react";
import { handleApiError } from "@/shared/api";
import { useToast } from "@/shared/ui";
import {
  disconnectTelegram,
  generateConnectionCode,
  getTelegramStatus,
} from "@/entities/telegram";
import { STATUS_POLL_INTERVAL_MS } from "../lib/constants";
import { parseUtcDate, statusToState } from "../lib/helpers";
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

    let cancelled = false;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;

    const expiryTimer = setTimeout(() => {
      cancelled = true;
      clearTimeout(pollTimer);
      setState({ status: "not-connected", isCodeExpired: true });
    }, Math.max(0, expiresAtMs - Date.now()));

    // Chained timeouts (not setInterval) so slow responses never overlap
    async function poll(): Promise<void> {
      try {
        const status = await getTelegramStatus();
        if (cancelled) return;
        if (status.connected) {
          setState(statusToState(status));
          showToast("Telegram connected.", "success");
          return;
        }
      } catch {
        // Transient failure: keep polling until the code expires
      }
      if (!cancelled) pollTimer = setTimeout(() => void poll(), STATUS_POLL_INTERVAL_MS);
    }

    pollTimer = setTimeout(() => void poll(), STATUS_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearTimeout(pollTimer);
      clearTimeout(expiryTimer);
    };
  }, [pendingCode, expiresAtMs, showToast]);

  const connect = useCallback(async (): Promise<void> => {
    setIsGenerating(true);
    try {
      const result = await generateConnectionCode();
      setState({
        status: "awaiting-link",
        code: result.code,
        expiresAtMs: parseUtcDate(result.expires_at).getTime(),
      });
    } catch (error: unknown) {
      handleApiError(error, showToast);
    } finally {
      setIsGenerating(false);
    }
  }, [showToast]);

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
