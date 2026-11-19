import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { TelegramSection } from "@/features/telegram-connect";
import { renderWithProviders } from "./utils";
import {
  mockConnectionCode,
  mockTelegramStatusConnected,
  mockTelegramStatusNotConnected,
} from "./mocks/handlers";
import { server } from "./setup";

// Fixed "now" in UTC. Code expiry timestamps below are naive UTC (no "Z"),
// exactly like the backend emits them, so the tests only pass if they are
// parsed as UTC — independent of the machine's timezone.
const NOW = new Date("2026-03-10T12:00:00Z");
const POLL_INTERVAL_MS = 3000;

type StatusPayload =
  | typeof mockTelegramStatusNotConnected
  | typeof mockTelegramStatusConnected;

/**
 * Serve GET /telegram/status from a script: the n-th request gets the n-th
 * payload (the last one repeats). Returns a live counter of requests made.
 */
function mockStatusSequence(...payloads: StatusPayload[]): { count: () => number } {
  let calls = 0;
  server.use(
    http.get("*/api/v1/telegram/status", () => {
      const payload = payloads[Math.min(calls, payloads.length - 1)];
      calls += 1;
      return HttpResponse.json(payload);
    }),
  );
  return { count: () => calls };
}

/** Advance fake time and flush the resulting fetches / state updates. */
async function advance(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

function setupUser() {
  return userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(NOW);
  localStorage.setItem("jobbi_token", "test-token");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("TelegramSection", () => {
  it('renders "Not connected" with a connect button initially', async () => {
    renderWithProviders(<TelegramSection />);

    expect(await screen.findByText("Not connected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect Telegram" })).toBeInTheDocument();
  });

  it("renders the linked username when already connected", async () => {
    mockStatusSequence(mockTelegramStatusConnected);

    renderWithProviders(<TelegramSection />);

    expect(await screen.findByText("@jobbi_tester")).toBeInTheDocument();
    expect(screen.getByText(/Connected as/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeInTheDocument();
  });

  it("shows an error with retry when the status request fails", async () => {
    let calls = 0;
    server.use(
      http.get("*/api/v1/telegram/status", () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ detail: "boom" }, { status: 500 })
          : HttpResponse.json(mockTelegramStatusNotConnected);
      }),
    );
    const user = setupUser();

    renderWithProviders(<TelegramSection />);

    expect(await screen.findByText("Could not load Telegram status.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("Not connected")).toBeInTheDocument();
  });

  it("clicking connect shows the code and linking instructions", async () => {
    const user = setupUser();
    renderWithProviders(<TelegramSection />);

    await user.click(await screen.findByRole("button", { name: "Connect Telegram" }));

    expect(await screen.findByText(mockConnectionCode.code)).toBeInTheDocument();
    expect(screen.getByText(/Open the Jobbi bot in Telegram/)).toBeInTheDocument();
    expect(screen.getByText("/start")).toBeInTheDocument();
    expect(screen.getByText(/Code expires at/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  it("polling detects the link, shows the username, and stops polling", async () => {
    // 1: initial load, 2: first poll (still waiting), 3: second poll (linked)
    const status = mockStatusSequence(
      mockTelegramStatusNotConnected,
      mockTelegramStatusNotConnected,
      mockTelegramStatusConnected,
    );
    const user = setupUser();
    renderWithProviders(<TelegramSection />);

    await user.click(await screen.findByRole("button", { name: "Connect Telegram" }));
    await screen.findByText(mockConnectionCode.code);
    expect(status.count()).toBe(1);

    await advance(POLL_INTERVAL_MS);
    expect(status.count()).toBe(2);
    expect(screen.getByText(mockConnectionCode.code)).toBeInTheDocument();

    await advance(POLL_INTERVAL_MS);
    expect(status.count()).toBe(3);
    expect(await screen.findByText("@jobbi_tester")).toBeInTheDocument();
    expect(screen.getByText(/Connected as/)).toBeInTheDocument();
    expect(screen.getByText("Telegram connected.")).toBeInTheDocument();
    expect(screen.queryByText(mockConnectionCode.code)).not.toBeInTheDocument();

    // No further status requests once connected
    await advance(POLL_INTERVAL_MS * 5);
    expect(status.count()).toBe(3);
  });

  it("code expiry stops polling and offers a new code", async () => {
    // Expires 5s after NOW: one poll at 3s, expiry at 5s, no poll at 6s.
    let codeRequests = 0;
    server.use(
      http.post("*/api/v1/telegram/connection-code", () => {
        codeRequests += 1;
        return codeRequests === 1
          ? HttpResponse.json(
              { code: "OLD111", expires_at: "2026-03-10T12:00:05" },
              { status: 201 },
            )
          : HttpResponse.json(
              { code: "NEW222", expires_at: "2026-03-10T12:15:00" },
              { status: 201 },
            );
      }),
    );
    const status = mockStatusSequence(mockTelegramStatusNotConnected);
    const user = setupUser();
    renderWithProviders(<TelegramSection />);

    await user.click(await screen.findByRole("button", { name: "Connect Telegram" }));
    await screen.findByText("OLD111");

    // Still valid after the first poll (a timezone-shifted parse would have
    // expired it immediately or kept it alive for hours)
    await advance(POLL_INTERVAL_MS);
    expect(status.count()).toBe(2);
    expect(screen.getByText("OLD111")).toBeInTheDocument();

    await advance(2000);
    expect(
      await screen.findByText("That code expired. Generate a new one to try again."),
    ).toBeInTheDocument();
    expect(screen.queryByText("OLD111")).not.toBeInTheDocument();
    expect(screen.getByText("Not connected")).toBeInTheDocument();

    // Polling stopped
    const countAtExpiry = status.count();
    await advance(POLL_INTERVAL_MS * 5);
    expect(status.count()).toBe(countAtExpiry);

    // A fresh code can be generated
    await user.click(screen.getByRole("button", { name: "Generate new code" }));
    expect(await screen.findByText("NEW222")).toBeInTheDocument();
    expect(codeRequests).toBe(2);
  });

  it("cancelling the code returns to not connected and stops polling", async () => {
    const status = mockStatusSequence(mockTelegramStatusNotConnected);
    const user = setupUser();
    renderWithProviders(<TelegramSection />);

    await user.click(await screen.findByRole("button", { name: "Connect Telegram" }));
    await screen.findByText(mockConnectionCode.code);

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(await screen.findByText("Not connected")).toBeInTheDocument();
    expect(screen.queryByText(mockConnectionCode.code)).not.toBeInTheDocument();
    expect(screen.queryByText(/That code expired/)).not.toBeInTheDocument();

    const countAfterCancel = status.count();
    await advance(POLL_INTERVAL_MS * 5);
    expect(status.count()).toBe(countAfterCancel);
  });

  it("unmounting stops polling", async () => {
    const status = mockStatusSequence(mockTelegramStatusNotConnected);
    const user = setupUser();
    const { unmount } = renderWithProviders(<TelegramSection />);

    await user.click(await screen.findByRole("button", { name: "Connect Telegram" }));
    await screen.findByText(mockConnectionCode.code);

    unmount();
    const countAtUnmount = status.count();
    await advance(POLL_INTERVAL_MS * 5);
    expect(status.count()).toBe(countAtUnmount);
  });

  describe("disconnect", () => {
    it("cancel closes the confirmation without disconnecting", async () => {
      mockStatusSequence(mockTelegramStatusConnected);
      let deleteCalls = 0;
      server.use(
        http.delete("*/api/v1/telegram/link", () => {
          deleteCalls += 1;
          return HttpResponse.json({ message: "Disconnected." });
        }),
      );
      const user = setupUser();
      renderWithProviders(<TelegramSection />);

      await user.click(await screen.findByRole("button", { name: "Disconnect" }));

      const confirm = screen.getByRole("group", { name: "Confirm disconnect" });
      expect(within(confirm).getByText(/Disconnect Telegram\?/)).toBeInTheDocument();
      const cancel = within(confirm).getByRole("button", { name: "Cancel" });
      expect(cancel).toHaveFocus();

      await user.click(cancel);

      expect(screen.queryByRole("group", { name: "Confirm disconnect" })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Disconnect" })).toHaveFocus();
      expect(screen.getByText("@jobbi_tester")).toBeInTheDocument();
      expect(deleteCalls).toBe(0);
    });

    it("confirming disconnects and returns to not connected", async () => {
      mockStatusSequence(mockTelegramStatusConnected);
      let deleteCalls = 0;
      server.use(
        http.delete("*/api/v1/telegram/link", () => {
          deleteCalls += 1;
          return HttpResponse.json({ message: "Disconnected." });
        }),
      );
      const user = setupUser();
      renderWithProviders(<TelegramSection />);

      await user.click(await screen.findByRole("button", { name: "Disconnect" }));
      await user.click(screen.getByRole("button", { name: "Yes, disconnect" }));

      expect(await screen.findByText("Not connected")).toBeInTheDocument();
      expect(screen.getByText("Telegram disconnected.")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Connect Telegram" })).toBeInTheDocument();
      expect(screen.queryByText("@jobbi_tester")).not.toBeInTheDocument();
      await waitFor(() => expect(deleteCalls).toBe(1));
    });
  });
});
