import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  getApplication,
  type ApplicationDetail,
} from "@/entities/application";
import {
  getChatHistory,
  clearChatHistory,
  sendChatMessage,
  type ChatMessage,
} from "@/entities/chat";
import { ChatWindow, ChatInput, QuickActionBar } from "@/features/chat-interface";
import { Button, colors, fonts, useToast } from "@/shared/ui";

/**
 * Chat page scoped to a single application.
 * This is a `page/` because it maps to the /applications/:id/chat route
 * and composes entities + features into a full-screen view.
 */
export function ChatPage() {
  const { id: applicationId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [application, setApplication] = useState<ApplicationDetail | null>(
    null,
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoadingApp, setIsLoadingApp] = useState(true);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  // Keep a ref to the abort controller so we can cancel on unmount
  const abortRef = useRef<AbortController | null>(null);

  // Fetch application detail and chat history in parallel on mount
  useEffect(() => {
    if (!applicationId) return;

    let cancelled = false;

    const fetchData = async (): Promise<void> => {
      try {
        const [app, history] = await Promise.all([
          getApplication(applicationId),
          getChatHistory(applicationId),
        ]);
        if (!cancelled) {
          setApplication(app);
          setMessages(history);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          showToast(
            err instanceof Error ? err.message : "Failed to load chat",
            "error",
          );
        }
      } finally {
        if (!cancelled) {
          setIsLoadingApp(false);
          setIsLoadingHistory(false);
        }
      }
    };

    void fetchData();

    return () => {
      cancelled = true;
    };
  }, [applicationId, showToast]);

  // Clean up abort controller on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const handleSend = useCallback(
    (content: string) => {
      if (!applicationId || isSending) return;

      setIsSending(true);
      setStreamingContent("");

      // Optimistically add user message to the list
      const optimisticUserMsg: ChatMessage = {
        id: `temp-${Date.now()}`,
        application_id: applicationId,
        role: "user",
        content,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optimisticUserMsg]);

      abortRef.current = sendChatMessage(
        applicationId,
        content,
        (token) => {
          setStreamingContent((prev) => (prev ?? "") + token);
        },
        () => {
          setStreamingContent(null);
          setIsSending(false);
          // Re-fetch history to get persisted messages from the server
          getChatHistory(applicationId)
            .then((history) => setMessages(history))
            .catch(() => {
              // History refresh failed — keep optimistic messages
            });
        },
        (detail) => {
          setStreamingContent(null);
          setIsSending(false);
          showToast(detail, "error");
        },
      );
    },
    [applicationId, isSending, showToast],
  );

  const handleClearHistory = useCallback(async (): Promise<void> => {
    if (!applicationId) return;

    try {
      await clearChatHistory(applicationId);
      setMessages([]);
      setShowClearConfirm(false);
      showToast("Chat history cleared.", "success");
    } catch (err: unknown) {
      showToast(
        err instanceof Error ? err.message : "Failed to clear history",
        "error",
      );
    }
  }, [applicationId, showToast]);

  if (!applicationId) {
    return null;
  }

  const hasCv = Boolean(application?.cv_id);
  const companyName = application?.company_name ?? "";
  const roleTitle = application?.role_title ?? "";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "calc(100vh - 64px)",
        fontFamily: fonts.base,
      }}
    >
      {/* Blinking cursor animation */}
      <style>{`
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
      `}</style>

      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0.75rem 1rem",
          borderBottom: `1px solid ${colors.borderLight}`,
          backgroundColor: colors.bgCard,
          flexShrink: 0,
          gap: "0.75rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", minWidth: 0 }}>
          <button
            onClick={() => navigate("/dashboard")}
            aria-label="Back to dashboard"
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              padding: "0.25rem",
              fontSize: "1.25rem",
              color: colors.textMuted,
              lineHeight: 1,
              flexShrink: 0,
            }}
          >
            &#x2190;
          </button>
          <div style={{ minWidth: 0 }}>
            {isLoadingApp ? (
              <span style={{ fontSize: "0.875rem", color: colors.textMuted }}>
                Loading...
              </span>
            ) : (
              <>
                <h1
                  style={{
                    margin: 0,
                    fontSize: "1rem",
                    fontWeight: 600,
                    color: colors.textPrimary,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {companyName} &mdash; {roleTitle}
                </h1>
                <span
                  style={{
                    fontSize: "0.75rem",
                    color: colors.textMuted,
                  }}
                >
                  {application?.cv_name ?? "No CV linked"}
                </span>
              </>
            )}
          </div>
        </div>

        <div style={{ display: "flex", gap: "0.5rem", flexShrink: 0 }}>
          {showClearConfirm ? (
            <>
              <Button
                variant="secondary"
                style={{
                  color: colors.error,
                  borderColor: colors.error,
                  fontSize: "0.75rem",
                  padding: "0.25rem 0.75rem",
                }}
                onClick={() => void handleClearHistory()}
              >
                Confirm
              </Button>
              <Button
                variant="secondary"
                style={{
                  fontSize: "0.75rem",
                  padding: "0.25rem 0.75rem",
                }}
                onClick={() => setShowClearConfirm(false)}
              >
                Cancel
              </Button>
            </>
          ) : (
            <Button
              variant="secondary"
              style={{
                fontSize: "0.75rem",
                padding: "0.25rem 0.75rem",
              }}
              onClick={() => setShowClearConfirm(true)}
              disabled={messages.length === 0}
            >
              Clear History
            </Button>
          )}
        </div>
      </div>

      {/* Messages area */}
      <ChatWindow
        messages={messages}
        streamingContent={streamingContent}
        isLoading={isLoadingHistory}
      />

      {/* Quick actions */}
      {!isLoadingApp && application && (
        <QuickActionBar
          onAction={handleSend}
          hasCv={hasCv}
          companyName={companyName}
          roleTitle={roleTitle}
        />
      )}

      {/* Input */}
      <ChatInput onSend={handleSend} disabled={isSending} />
    </div>
  );
}
