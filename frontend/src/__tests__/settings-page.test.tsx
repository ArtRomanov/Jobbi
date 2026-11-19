import { StrictMode } from "react";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
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

/** Make `Intl.DateTimeFormat().resolvedOptions().timeZone` report `timeZone`. */
function mockBrowserTimezone(timeZone: string): void {
  vi.restoreAllMocks();
  const real = new Intl.DateTimeFormat().resolvedOptions();
  vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockReturnValue({
    ...real,
    timeZone,
  });
}

/** Wait until the profile has loaded and the form is rendered. */
async function waitForForm(): Promise<void> {
  await screen.findByRole("button", { name: "Save Changes" });
}

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
  currentUser = mockUser;
  // Pin the "browser" timezone so detection is independent of the machine
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

    // Give any stray effect a chance to fire a second request
    await new Promise((resolve) => setTimeout(resolve, 50));
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

    // Give the discarded first effect run a chance to fire a stray PATCH
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(patches).toEqual([{ timezone: DETECTED_TIMEZONE }]);
  });

  it("does not auto-save when the timezone is already set", async () => {
    const patches = capturePatches();

    renderWithProviders(<SettingsPage />);
    await waitForForm();

    await new Promise((resolve) => setTimeout(resolve, 50));
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
