const baseUrl =
  import.meta.env.VITE_API_URL ?? "http://localhost:8000";

/**
 * Send a chat message and consume the SSE streaming response.
 *
 * Uses raw fetch() instead of apiClient because the response is an SSE stream,
 * not JSON. Each SSE frame has an `event:` line and a `data:` line.
 */
export function sendChatMessage(
  applicationId: string,
  content: string,
  onToken: (text: string) => void,
  onDone: () => void,
  onError: (detail: string) => void,
): AbortController {
  const controller = new AbortController();

  const token = localStorage.getItem("jobbi_token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  fetch(`${baseUrl}/api/v1/applications/${applicationId}/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({ content }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const body = await response.text().catch(() => "Unknown error");
        onError(`Request failed (${String(response.status)}): ${body}`);
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        onError("No response body");
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Process complete SSE frames (separated by double newlines)
        const frames = buffer.split("\n\n");
        // Keep the last (possibly incomplete) chunk in the buffer
        buffer = frames.pop() ?? "";

        for (const frame of frames) {
          if (!frame.trim()) continue;

          let eventType = "message";
          let data = "";

          for (const line of frame.split("\n")) {
            if (line.startsWith("event: ")) {
              eventType = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              data = line.slice(6);
            }
          }

          switch (eventType) {
            case "token":
              onToken(data);
              break;
            case "done":
              onDone();
              return;
            case "error":
              onError(data || "Stream error");
              return;
          }
        }
      }

      // If stream ended without explicit done event, treat as done
      onDone();
    })
    .catch((err: unknown) => {
      if (err instanceof DOMException && err.name === "AbortError") {
        // Intentional abort — do nothing
        return;
      }
      onError(err instanceof Error ? err.message : "Network error");
    });

  return controller;
}
