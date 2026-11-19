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
const CODE_TTL_MS = 10 * 60 * 1000;

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

/** Serve a single fixed connection code. */
function mockConnectionCodeOnce(code: string, expiresAt: string): void {
  server.use(
    http.post("*/api/v1/telegram/connection-code", () =>
      HttpResponse.json({ code, expires_at: expiresAt }, { status: 201 }),
    ),
  );
}

/** Count DELETE /telegram/link requests. */
function mockDisconnect(): { count: () => number } {
  let calls = 0;
  server.use(
    http.delete("*/api/v1/telegram/link", () => {
      calls += 1;
      return HttpResponse.json({ message: "Disconnected." });
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

/** The single aria-live "Status: …" line that announces every state change. */
function getStatusRegion(): HTMLElement {
  const region = screen.getByText(/^Status:/).closest<HTMLElement>('[aria-live="polite"]');
  if (!region) throw new Error("Status live region not found");
  return region;
}

async function expectStatus(label: string): Promise<void> {
  await waitFor(() => expect(getStatusRegion()).toHaveTextContent(`Status: ${label}`));
}

function getHeading(): HTMLElement {
  return screen.getByRole("heading", { name: "Telegram" });
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

    await expectStatus("Not connected");
    expect(screen.getByRole("button", { name: "Connect Telegram" })).toBeInTheDocument();
    // The initial status load never steals focus
    expect(getHeading()).not.toHaveFocus();
  });

  it("renders the linked username once, in the status line, when already connected", async () => {
    mockStatusSequence(mockTelegramStatusConnected);

    renderWithProviders(<TelegramSection />);

    await expectStatus("Connected as @jobbi_tester");
    // The connected panel no longer repeats the username
    expect(screen.getAllByText(/@jobbi_tester/)).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeInTheDocument();
    expect(getHeading()).not.toHaveFocus();
  });

  it("shows an error in the status line with retry when the status request fails", async () => {
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

    await expectStatus("Could not load Telegram status.");
    // One live region only — no nested role="alert" competing with it
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Try again" }));

    await expectStatus("Not connected");
    expect(calls).toBe(2);
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
    await expectStatus("Not connected yet — waiting for your code");
  });

  it("moves focus to the section heading after Connect swaps the panel", async () => {
    const user = setupUser();
    renderWithProviders(<TelegramSection />);

    await user.click(await screen.findByRole("button", { name: "Connect Telegram" }));
    await screen.findByText(mockConnectionCode.code);

    await waitFor(() => expect(getHeading()).toHaveFocus());
    expect(getHeading()).toHaveAttribute("tabindex", "-1");
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
    await expectStatus("Connected as @jobbi_tester");
    expect(screen.getByText("Telegram connected.")).toBeInTheDocument();
    expect(screen.queryByText(mockConnectionCode.code)).not.toBeInTheDocument();

    // No further status requests once connected
    await advance(POLL_INTERVAL_MS * 5);
    expect(status.count()).toBe(3);
  });

  it("code expiry runs one final check, stops polling, and offers a new code", async () => {
    // Expires 5s after NOW: poll at 3s, final check at 5s, nothing at 6s.
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
    await expectStatus("Not connected (code expired)");
    expect(screen.getByText("Generate a new code to try again.")).toBeInTheDocument();
    expect(screen.queryByText("OLD111")).not.toBeInTheDocument();
    expect(screen.queryByText("Telegram connected.")).not.toBeInTheDocument();
    // initial load + one poll + exactly one final check at expiry
    expect(status.count()).toBe(3);

    // Polling stopped
    await advance(POLL_INTERVAL_MS * 5);
    expect(status.count()).toBe(3);

    // A fresh code can be generated
    await user.click(screen.getByRole("button", { name: "Generate new code" }));
    expect(await screen.findByText("NEW222")).toBeInTheDocument();
    expect(codeRequests).toBe(2);
  });

  it("a link made in the last seconds before expiry ends connected, not expired", async () => {
    mockConnectionCodeOnce("LATE33", "2026-03-10T12:00:05");
    // initial load, poll at 3s (still waiting), final check at expiry (linked)
    const status = mockStatusSequence(
      mockTelegramStatusNotConnected,
      mockTelegramStatusNotConnected,
      mockTelegramStatusConnected,
    );
    const user = setupUser();
    renderWithProviders(<TelegramSection />);

    await user.click(await screen.findByRole("button", { name: "Connect Telegram" }));
    await screen.findByText("LATE33");

    await advance(POLL_INTERVAL_MS);
    expect(status.count()).toBe(2);

    await advance(2000);
    await expectStatus("Connected as @jobbi_tester");
    expect(screen.getByText("Telegram connected.")).toBeInTheDocument();
    expect(screen.queryByText(/code expired/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeInTheDocument();
    expect(status.count()).toBe(3);

    await advance(POLL_INTERVAL_MS * 5);
    expect(status.count()).toBe(3);
  });

  it("caps the expiry timer at the 10-minute server TTL", async () => {
    // A skewed expires_at two hours out must not keep the code alive for hours
    mockConnectionCodeOnce("SKEW44", "2026-03-10T14:00:00");
    const status = mockStatusSequence(mockTelegramStatusNotConnected);
    const user = setupUser();
    renderWithProviders(<TelegramSection />);

    await user.click(await screen.findByRole("button", { name: "Connect Telegram" }));
    await screen.findByText("SKEW44");

    await advance(CODE_TTL_MS - 1000);
    expect(screen.getByText("SKEW44")).toBeInTheDocument();

    await advance(2000);
    await expectStatus("Not connected (code expired)");

    const countAtExpiry = status.count();
    await advance(POLL_INTERVAL_MS * 5);
    expect(status.count()).toBe(countAtExpiry);
  });

  it("cancelling the code returns to not connected and stops polling", async () => {
    const status = mockStatusSequence(mockTelegramStatusNotConnected);
    const user = setupUser();
    renderWithProviders(<TelegramSection />);

    await user.click(await screen.findByRole("button", { name: "Connect Telegram" }));
    await screen.findByText(mockConnectionCode.code);

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await expectStatus("Not connected");
    expect(screen.queryByText(mockConnectionCode.code)).not.toBeInTheDocument();
    expect(screen.queryByText(/code expired/)).not.toBeInTheDocument();
    expect(getHeading()).toHaveFocus();

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
      const deletes = mockDisconnect();
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
      await expectStatus("Connected as @jobbi_tester");
      expect(deletes.count()).toBe(0);
    });

    it("Escape closes the confirmation without disconnecting", async () => {
      mockStatusSequence(mockTelegramStatusConnected);
      const deletes = mockDisconnect();
      const user = setupUser();
      renderWithProviders(<TelegramSection />);

      await user.click(await screen.findByRole("button", { name: "Disconnect" }));
      expect(screen.getByRole("group", { name: "Confirm disconnect" })).toBeInTheDocument();

      await user.keyboard("{Escape}");

      expect(screen.queryByRole("group", { name: "Confirm disconnect" })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Disconnect" })).toHaveFocus();
      await expectStatus("Connected as @jobbi_tester");
      expect(deletes.count()).toBe(0);
    });

    it("confirming disconnects and returns to not connected", async () => {
      mockStatusSequence(mockTelegramStatusConnected);
      const deletes = mockDisconnect();
      const user = setupUser();
      renderWithProviders(<TelegramSection />);

      await user.click(await screen.findByRole("button", { name: "Disconnect" }));
      await user.click(screen.getByRole("button", { name: "Yes, disconnect" }));

      await expectStatus("Not connected");
      expect(screen.getByText("Telegram disconnected.")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Connect Telegram" })).toBeInTheDocument();
      expect(screen.queryByText(/@jobbi_tester/)).not.toBeInTheDocument();
      expect(getHeading()).toHaveFocus();
      expect(deletes.count()).toBe(1);
    });
  });
});
