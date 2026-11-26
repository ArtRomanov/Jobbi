import { StrictMode } from "react";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { MockInstance } from "vitest";
import { SettingsPage } from "@/pages/settings";
import { renderWithProviders } from "./utils";
import { mockUser } from "./mocks/handlers";
import { server } from "./setup";

const DETECTED_TIMEZONE = "Asia/Tokyo";

type MockUser = Omit<typeof mockUser, "timezone"> & { timezone: string | null };

/** The user GET /users/me currently serves; PATCH responses build on it. */
let currentUser: MockUser = mockUser;

function serveUser(user: MockUser): void {
  currentUser = user;
  server.use(http.get("*/api/v1/users/me", () => HttpResponse.json(user)));
}

/** Record every PATCH /users/me body; responds like the real endpoint. */
function capturePatches(): Array<Record<string, unknown>> {
  const bodies: Array<Record<string, unknown>> = [];
  server.use(
    http.patch("*/api/v1/users/me", async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      bodies.push(body);
      return HttpResponse.json({ ...currentUser, ...body });
    }),
  );
  return bodies;
}

/** Captured before any spy is installed. */
const REAL_RESOLVED_OPTIONS = new Intl.DateTimeFormat().resolvedOptions();

let resolvedOptionsSpy: MockInstance<() => Intl.ResolvedDateTimeFormatOptions>;

/** Make `Intl.DateTimeFormat().resolvedOptions().timeZone` report `timeZone`. */
function mockBrowserTimezone(timeZone: string): void {
  resolvedOptionsSpy.mockReturnValue({ ...REAL_RESOLVED_OPTIONS, timeZone });
}

/** Flush pending effects and microtasks so a stray request would be recorded. */
async function flushEffects(): Promise<void> {
  await act(() => Promise.resolve());
}

/** Wait until the profile has loaded and the form is rendered. */
async function waitForForm(): Promise<void> {
  await screen.findByRole("button", { name: "Save Changes" });
}

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
  currentUser = mockUser;
  // Pin the "browser" timezone so detection is independent of the machine
  resolvedOptionsSpy = vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions");
  mockBrowserTimezone(DETECTED_TIMEZONE);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SettingsPage — timezone and daily summary", () => {
  it("shows the timezone and summary time fields with saved values", async () => {
    renderWithProviders(<SettingsPage />);
    await waitForForm();

    const timezone = screen.getByLabelText("Timezone");
    const summaryTime = screen.getByLabelText("Daily Summary Time");

    expect(timezone).toHaveValue("Europe/Berlin");
    expect(summaryTime).toHaveAttribute("type", "time");
    expect(summaryTime).toHaveValue("10:00");
  });

  it("auto-detects and saves the timezone exactly once when it is not set", async () => {
    serveUser({ ...mockUser, timezone: null });
    const patches = capturePatches();

    renderWithProviders(<SettingsPage />);
    await waitForForm();

    expect(
      await screen.findByText(`Timezone detected and saved: ${DETECTED_TIMEZONE}.`),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Timezone")).toHaveValue(DETECTED_TIMEZONE);
    expect(patches).toEqual([{ timezone: DETECTED_TIMEZONE }]);

    // The toast means the auto-save settled; a stray second effect would fire now
    await flushEffects();
    expect(patches).toHaveLength(1);
  });

  it("auto-saves the detected timezone exactly once under React StrictMode", async () => {
    serveUser({ ...mockUser, timezone: null });
    const patches = capturePatches();

    // StrictMode mounts, unmounts, and re-mounts: effects run twice in dev
    renderWithProviders(
      <StrictMode>
        <SettingsPage />
      </StrictMode>,
    );
    await waitForForm();

    expect(
      await screen.findByText(`Timezone detected and saved: ${DETECTED_TIMEZONE}.`),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Timezone")).toHaveValue(DETECTED_TIMEZONE);

    // The toast means the auto-save settled; flush the discarded first effect run
    await flushEffects();
    expect(patches).toEqual([{ timezone: DETECTED_TIMEZONE }]);
  });

  it("does not auto-save when the timezone is already set", async () => {
    const patches = capturePatches();

    renderWithProviders(<SettingsPage />);
    // The form renders only after GET /users/me resolved; flush its effects
    await waitForForm();
    await flushEffects();

    expect(patches).toHaveLength(0);
    expect(screen.queryByText(/Timezone detected and saved/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Timezone")).toHaveValue("Europe/Berlin");
  });

  it("prefills the detected timezone as unsaved when the auto-save fails", async () => {
    serveUser({ ...mockUser, timezone: null });
    const patches: Array<Record<string, unknown>> = [];
    server.use(
      http.patch("*/api/v1/users/me", async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        patches.push(body);
        // First call (auto-save) fails, the manual save succeeds
        return patches.length === 1
          ? HttpResponse.json({ detail: "boom" }, { status: 500 })
          : HttpResponse.json({ ...mockUser, ...body });
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<SettingsPage />);
    await waitForForm();

    expect(screen.getByLabelText("Timezone")).toHaveValue(DETECTED_TIMEZONE);
    expect(screen.queryByText(/Timezone detected and saved/)).not.toBeInTheDocument();
    expect(
      await screen.findByText(
        `Detected timezone ${DETECTED_TIMEZONE} but couldn't save it. Click "Save Changes" to save.`,
      ),
    ).toBeInTheDocument();

    // The unsaved detected timezone counts as a change
    expect(screen.getByRole("button", { name: "Save Changes" })).not.toHaveAttribute("aria-disabled");
    await user.click(screen.getByRole("button", { name: "Save Changes" }));

    await waitFor(() => expect(patches).toHaveLength(2));
    expect(patches[1]).toEqual({ timezone: DETECTED_TIMEZONE });
  });

  it("offers no empty timezone choice once a timezone is saved", async () => {
    renderWithProviders(<SettingsPage />);
    await waitForForm();

    const timezone = screen.getByLabelText("Timezone");
    expect(within(timezone).queryByRole("option", { name: "Not set" })).not.toBeInTheDocument();
    expect(
      within(timezone).queryByRole("option", { name: "Select timezone..." }),
    ).not.toBeInTheDocument();
    expect(within(timezone).queryByRole("option", { name: "" })).not.toBeInTheDocument();
  });

  it("requires a timezone when none is saved and none can be detected", async () => {
    serveUser({ ...mockUser, timezone: null });
    // Browser can't report a timezone, so nothing is auto-saved
    mockBrowserTimezone("");
    const patches = capturePatches();
    const user = userEvent.setup();

    renderWithProviders(<SettingsPage />);
    await waitForForm();

    const timezone = screen.getByLabelText("Timezone");
    expect(timezone).toHaveValue("");
    expect(
      within(timezone).getByRole("option", { name: "Select timezone..." }),
    ).toBeInTheDocument();

    // Save needs a change first; any other field will do
    await user.type(screen.getByLabelText("Desired Role"), "x");
    await user.click(screen.getByRole("button", { name: "Save Changes" }));

    expect(
      await screen.findByText("Timezone is required for the daily summary"),
    ).toBeInTheDocument();
    expect(timezone).toHaveAttribute("aria-invalid", "true");
    expect(patches).toHaveLength(0);
  });

  it("Save sends the edited timezone and summary time", async () => {
    const patches = capturePatches();
    const user = userEvent.setup();

    renderWithProviders(<SettingsPage />);
    await waitForForm();

    await user.selectOptions(screen.getByLabelText("Timezone"), "America/New_York");
    const summaryTime = screen.getByLabelText("Daily Summary Time");
    await user.clear(summaryTime);
    await user.type(summaryTime, "08:30");
    expect(summaryTime).toHaveValue("08:30");

    await user.click(screen.getByRole("button", { name: "Save Changes" }));

    expect(await screen.findByText("Profile updated.")).toBeInTheDocument();
    expect(patches).toEqual([{ timezone: "America/New_York", summary_time: "08:30" }]);
  });
});

describe("SettingsPage — Save is active only with changes", () => {
  function getSave(): HTMLElement {
    return screen.getByRole("button", { name: "Save Changes" });
  }

  it("is off after load, on after an edit and off again after reverting it", async () => {
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);
    await waitForForm();

    expect(getSave()).toHaveAttribute("aria-disabled", "true");
    await user.type(screen.getByLabelText("Full Name *"), "x");
    expect(getSave()).not.toHaveAttribute("aria-disabled");
    await user.type(screen.getByLabelText("Full Name *"), "{Backspace}");
    expect(getSave()).toHaveAttribute("aria-disabled", "true");

    await user.selectOptions(screen.getByLabelText("Timezone"), "America/New_York");
    expect(getSave()).not.toHaveAttribute("aria-disabled");
    await user.selectOptions(screen.getByLabelText("Timezone"), "Europe/Berlin");
    expect(getSave()).toHaveAttribute("aria-disabled", "true");
  });

  it("is off again after a successful save and keeps focus", async () => {
    const patches = capturePatches();
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);
    await waitForForm();

    await user.type(screen.getByLabelText("Desired Role"), "Lead");
    await user.click(getSave());

    expect(await screen.findByText("Profile updated.")).toBeInTheDocument();
    expect(patches).toHaveLength(1);
    expect(getSave()).toHaveAttribute("aria-disabled", "true");
    expect(getSave()).toHaveFocus();
  });

  it("sends nothing when the aria-disabled Save is pressed", async () => {
    const patches = capturePatches();
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);
    await waitForForm();

    await user.click(getSave());
    await user.type(screen.getByLabelText("Desired Role"), "{Enter}");
    await flushEffects();

    expect(patches).toHaveLength(0);
    expect(screen.queryByText("No changes to save.")).not.toBeInTheDocument();
  });
});
