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

// Fixed "now" in UTC. Expiry timestamps below mix Z-suffixed and naive forms;
// the UI only rejects an unparseable expires_at (the 10-minute TTL drives
// expiry), so naive-as-UTC parsing is covered in telegram-helpers.test.ts.
const NOW = new Date("2026-03-10T12:00:00Z");
const POLL_INTERVAL_MS = 3000;
const CODE_TTL_MS = 10 * 60 * 1000;
const EXPIRY_GRACE_MS = 3000;

const STATUS_URL = "*/api/v1/telegram/status";
const CODE_URL = "*/api/v1/telegram/connection-code";
const LINK_URL = "*/api/v1/telegram/link";

type StatusPayload =
  | typeof mockTelegramStatusNotConnected
  | typeof mockTelegramStatusConnected;

/**
 * Route `method url` to `respond`, which gets the 1-based number of the
 * request. Returns a live counter of requests made.
 */
function mockCountedRoute(
  method: "get" | "post" | "delete",
  url: string,
  respond: (call: number) => Response | Promise<Response>,
): { count: () => number } {
  let calls = 0;
  server.use(
    http[method](url, () => {
      calls += 1;
      return respond(calls);
    }),
  );
  return { count: () => calls };
}

/**
 * Serve GET /telegram/status from a script: the n-th request gets the n-th
 * payload (the last one repeats). Returns a live counter of requests made.
 */
function mockStatusSequence(...payloads: StatusPayload[]): { count: () => number } {
  return mockCountedRoute("get", STATUS_URL, (call) =>
    HttpResponse.json(payloads[Math.min(call, payloads.length) - 1]),
  );
}

/**
 * Serve GET /telegram/status as "not connected" until `setConnected(true)`.
 * Returns a live counter of requests made.
 */
function mockStatusSwitch(): { count: () => number; setConnected: (value: boolean) => void } {
  let isConnected = false;
  const { count } = mockCountedRoute("get", STATUS_URL, () =>
    HttpResponse.json(isConnected ? mockTelegramStatusConnected : mockTelegramStatusNotConnected),
  );
  return {
    count,
    setConnected: (value) => {
      isConnected = value;
    },
  };
}

/** Serve one fixed connection code for the next request only. */
function mockConnectionCodeOnce(code: string, expiresAt: string): void {
  server.use(
    http.post(
      CODE_URL,
      () => HttpResponse.json({ code, expires_at: expiresAt }, { status: 201 }),
      { once: true },
    ),
  );
}

/** Count DELETE /telegram/link requests. */
function mockDisconnect(): { count: () => number } {
  return mockCountedRoute("delete", LINK_URL, () =>
    HttpResponse.json({ message: "Disconnected." }),
  );
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

/** Same local "HH:MM" format the code panel uses. */
function clockTime(epochMs: number): string {
  return new Date(epochMs).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
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
    const status = mockCountedRoute("get", STATUS_URL, (call) =>
      call === 1
        ? HttpResponse.json({ detail: "boom" }, { status: 500 })
        : HttpResponse.json(mockTelegramStatusNotConnected),
    );
    const user = setupUser();

    renderWithProviders(<TelegramSection />);

    await expectStatus("Could not load Telegram status.");
    // One live region only — no nested role="alert" competing with it
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Try again" }));

    await expectStatus("Not connected");
    expect(status.count()).toBe(2);
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
    const codeRequests = mockCountedRoute("post", CODE_URL, (call) =>
      call === 1
        ? // Naive (legacy backend format) is accepted; expiry follows the TTL
          HttpResponse.json({ code: "OLD111", expires_at: "2026-03-10T12:10:00" }, { status: 201 })
        : HttpResponse.json({ code: "NEW222", expires_at: "2026-03-10T12:25:00Z" }, { status: 201 }),
    );
    const status = mockStatusSwitch();
    const user = setupUser();
    renderWithProviders(<TelegramSection />);

    await user.click(await screen.findByRole("button", { name: "Connect Telegram" }));
    await screen.findByText("OLD111");

    // Still valid at the full TTL: the final check waits out the grace period
    await advance(CODE_TTL_MS);
    expect(screen.getByText("OLD111")).toBeInTheDocument();

    await advance(EXPIRY_GRACE_MS);
    await expectStatus("Not connected (code expired)");
    expect(screen.getByText("Generate a new code to try again.")).toBeInTheDocument();
    expect(screen.queryByText("OLD111")).not.toBeInTheDocument();
    expect(screen.queryByText("Telegram connected.")).not.toBeInTheDocument();

    // Polling stopped
    const countAtExpiry = status.count();
    await advance(POLL_INTERVAL_MS * 5);
    expect(status.count()).toBe(countAtExpiry);

    // A fresh code can be generated
    await user.click(screen.getByRole("button", { name: "Generate new code" }));
    expect(await screen.findByText("NEW222")).toBeInTheDocument();
    expect(codeRequests.count()).toBe(2);
  });

  it("a link committed after the last poll is caught by the final check (grace period)", async () => {
    const status = mockStatusSwitch();
    const user = setupUser();
    renderWithProviders(<TelegramSection />);

    await user.click(await screen.findByRole("button", { name: "Connect Telegram" }));
    await screen.findByText(mockConnectionCode.code);

    // Every poll up to the nominal expiry still says "not linked"…
    await advance(CODE_TTL_MS);
    expect(screen.getByText(mockConnectionCode.code)).toBeInTheDocument();
    // …then the server commits the link at the very last moment
    status.setConnected(true);

    await advance(EXPIRY_GRACE_MS);
    await expectStatus("Connected as @jobbi_tester");
    expect(screen.getByText("Telegram connected.")).toBeInTheDocument();
    expect(screen.queryByText(/code expired/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeInTheDocument();

    const countAfterLink = status.count();
    await advance(POLL_INTERVAL_MS * 5);
    expect(status.count()).toBe(countAfterLink);
  });

  it("a client clock running 3 minutes fast does not expire the code early", async () => {
    // Server time is 3 min behind the client, so the server's 10-minute code
    // "expires" only 7 minutes after the client's now (Z-suffixed UTC).
    const clockSkewMs = 3 * 60 * 1000;
    const serverExpiresAt = new Date(NOW.getTime() - clockSkewMs + CODE_TTL_MS).toISOString();
    expect(serverExpiresAt).toBe("2026-03-10T12:07:00.000Z");
    mockConnectionCodeOnce("FAST55", serverExpiresAt);
    const status = mockStatusSwitch();
    const user = setupUser();
    renderWithProviders(<TelegramSection />);

    await user.click(await screen.findByRole("button", { name: "Connect Telegram" }));
    await screen.findByText("FAST55");

    // The label follows the user's clock (receipt + TTL), not the skewed expires_at
    expect(
      screen.getByText(new RegExp(`Code expires at ${clockTime(NOW.getTime() + CODE_TTL_MS)}\\.`)),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(new RegExp(`Code expires at ${clockTime(Date.parse(serverExpiresAt))}\\.`)),
    ).not.toBeInTheDocument();

    // Past the skewed expires_at: the server still accepts the code, keep polling
    await advance(CODE_TTL_MS - clockSkewMs + 30_000);
    expect(screen.getByText("FAST55")).toBeInTheDocument();
    expect(screen.queryByText(/code expired/)).not.toBeInTheDocument();
    const countMidway = status.count();
    await advance(POLL_INTERVAL_MS * 2);
    expect(status.count()).toBeGreaterThan(countMidway);

    // The real 10-minute lifetime (from when the code arrived) still applies
    await advance(CODE_TTL_MS);
    await expectStatus("Not connected (code expired)");
  });

  it("ignores a far-future expires_at and expires after the 10-minute TTL", async () => {
    // A slow client clock (expires_at two hours out) must not keep the code alive for hours
    mockConnectionCodeOnce("SKEW44", "2026-03-10T14:00:00");
    const status = mockStatusSwitch();
    const user = setupUser();
    renderWithProviders(<TelegramSection />);

    await user.click(await screen.findByRole("button", { name: "Connect Telegram" }));
    await screen.findByText("SKEW44");

    await advance(CODE_TTL_MS - 1000);
    expect(screen.getByText("SKEW44")).toBeInTheDocument();

    await advance(EXPIRY_GRACE_MS + 2000);
    await expectStatus("Not connected (code expired)");

    const countAtExpiry = status.count();
    await advance(POLL_INTERVAL_MS * 5);
    expect(status.count()).toBe(countAtExpiry);
  });

  it("shows an error and stays not connected when expires_at is unparseable", async () => {
    mockConnectionCodeOnce("BAD666", "not-a-date");
    const user = setupUser();
    renderWithProviders(<TelegramSection />);

    await user.click(await screen.findByRole("button", { name: "Connect Telegram" }));

    expect(await screen.findByText("Something went wrong. Please try again.")).toBeInTheDocument();
    expect(screen.queryByText("BAD666")).not.toBeInTheDocument();
    await expectStatus("Not connected");
  });

  it("cancelling the code returns to not connected, checks once, and stops polling", async () => {
    const status = mockStatusSwitch();
    const user = setupUser();
    renderWithProviders(<TelegramSection />);

    await user.click(await screen.findByRole("button", { name: "Connect Telegram" }));
    await screen.findByText(mockConnectionCode.code);
    const countBeforeCancel = status.count();

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await expectStatus("Not connected");
    expect(screen.queryByText(mockConnectionCode.code)).not.toBeInTheDocument();
    expect(screen.queryByText(/code expired/)).not.toBeInTheDocument();
    expect(getHeading()).toHaveFocus();

    // Exactly one final status check, then nothing
    await waitFor(() => expect(status.count()).toBe(countBeforeCancel + 1));
    await advance(POLL_INTERVAL_MS * 5);
    expect(status.count()).toBe(countBeforeCancel + 1);
    await expectStatus("Not connected");
    expect(screen.queryByText("Telegram connected.")).not.toBeInTheDocument();
  });

  it("cancelling after the code was already sent ends connected", async () => {
    const status = mockStatusSwitch();
    const user = setupUser();
    renderWithProviders(<TelegramSection />);

    await user.click(await screen.findByRole("button", { name: "Connect Telegram" }));
    await screen.findByText(mockConnectionCode.code);

    // The user sent the code to the bot, then clicked Cancel before the next poll
    status.setConnected(true);
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await expectStatus("Connected as @jobbi_tester");
    expect(screen.getByText("Telegram connected.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeInTheDocument();

    const countAfterLink = status.count();
    await advance(POLL_INTERVAL_MS * 5);
    expect(status.count()).toBe(countAfterLink);
  });

  it("a new code generated during the cancel check is not overridden by it", async () => {
    // Hold the first status request made after Cancel (the cancel check) until
    // the user has asked for a new code. Polls before Cancel are never held.
    let isHoldingNext = false;
    let releaseCheck: (() => void) | undefined;
    let isCheckAnswered = false;
    mockCountedRoute("get", STATUS_URL, async () => {
      if (!isHoldingNext) return HttpResponse.json(mockTelegramStatusNotConnected);
      isHoldingNext = false;
      await new Promise<void>((resolve) => {
        releaseCheck = resolve;
      });
      isCheckAnswered = true;
      return HttpResponse.json(mockTelegramStatusConnected);
    });
    const user = setupUser();
    renderWithProviders(<TelegramSection />);

    await user.click(await screen.findByRole("button", { name: "Connect Telegram" }));
    await screen.findByText(mockConnectionCode.code);
    isHoldingNext = true;
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(releaseCheck).toBeDefined());

    await user.click(screen.getByRole("button", { name: "Connect Telegram" }));
    await screen.findByText(mockConnectionCode.code);
    expect(isCheckAnswered).toBe(false);

    releaseCheck?.();
    await waitFor(() => expect(isCheckAnswered).toBe(true));
    await advance(100);
    // The stale "connected" answer must not override the fresh code
    expect(screen.getByText(mockConnectionCode.code)).toBeInTheDocument();
    expect(screen.queryByText("Telegram connected.")).not.toBeInTheDocument();
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
