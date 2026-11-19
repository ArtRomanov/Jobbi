import { useCallback, useEffect, useRef, useState } from "react";
import { handleApiError } from "@/shared/api";
import { useToast } from "@/shared/ui";
import {
  disconnectTelegram,
  generateConnectionCode,
  getTelegramStatus,
} from "@/entities/telegram";
import type { TelegramStatus } from "@/entities/telegram";
import { CODE_TTL_MS, EXPIRY_GRACE_MS, STATUS_POLL_INTERVAL_MS } from "../lib/constants";
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
 *
 * Expiry is timed as CODE_TTL_MS from when the code arrived (a relative
 * timer), not from `expires_at`, so a skewed client clock can't end polling
 * while the server still accepts the code. Both expiry and Cancel run one
 * final status check, so a link made at the last moment is not lost.
 */
export function useTelegramConnection(): UseTelegramConnectionResult {
  const { showToast } = useToast();
  const [state, setState] = useState<TelegramConnectionState>({ status: "loading" });
  const [reloadKey, setReloadKey] = useState(0);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const isMountedRef = useRef(false);
  // Bumped on every connect/cancel; a stale cancel check must not override a newer flow
  const flowSeqRef = useRef(0);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const markConnected = useCallback(
    (status: TelegramStatus): void => {
      setState(statusToState(status));
      showToast("Telegram connected.", "success");
    },
    [showToast],
  );

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

  // Primitive dep so the effect restarts only when a new code is issued
  const pendingCode = state.status === "awaiting-link" ? state.code : null;

  // Poll status while a code is on screen; stop on link, expiry, or unmount
  useEffect(() => {
    if (pendingCode === null) return;

    // `cancelled`: effect cleaned up (ignore everything). `isStopped`: polling
    // halted because the code expired (only the final check may settle state).
    let cancelled = false;
    let isStopped = false;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;

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

    // Relative timer from code receipt: immune to client clock skew
    const expiryTimer = setTimeout(() => void finalCheck(), CODE_TTL_MS + EXPIRY_GRACE_MS);

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
  }, [pendingCode, markConnected]);

  const connect = useCallback(async (): Promise<void> => {
    if (isGenerating) return;
    flowSeqRef.current += 1;
    setIsGenerating(true);
    try {
      const result = await generateConnectionCode();
      // expires_at is only a sanity check: reject a malformed payload
      if (Number.isNaN(parseUtcDate(result.expires_at).getTime())) {
        showToast("Something went wrong. Please try again.", "error");
        return;
      }
      // Displayed expiry = receipt + TTL on the user's own clock, matching the expiry timer
      setState({
        status: "awaiting-link",
        code: result.code,
        expiresAtMs: Date.now() + CODE_TTL_MS,
      });
    } catch (error: unknown) {
      handleApiError(error, showToast);
    } finally {
      setIsGenerating(false);
    }
  }, [isGenerating, showToast]);

  // Stop polling right away, then check once: the user may already have sent the code
  const cancelCode = useCallback((): void => {
    flowSeqRef.current += 1;
    const seq = flowSeqRef.current;
    setState({ status: "not-connected", isCodeExpired: false });

    async function cancelCheck(): Promise<void> {
      try {
        const status = await getTelegramStatus();
        if (!isMountedRef.current || seq !== flowSeqRef.current) return;
        if (status.connected) markConnected(status);
      } catch {
        // Stay "not connected"; the next page load will show the real status
      }
    }

    void cancelCheck();
  }, [markConnected]);

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
