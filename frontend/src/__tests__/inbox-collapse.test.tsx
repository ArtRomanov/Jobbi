import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { InboxPage } from "@/pages/inbox";
import { renderWithProviders } from "./utils";
import {
  mockVacancy,
  mockVacancyPageEmpty,
  mockVacancySource,
  mockVacancySourcesEmpty,
} from "./mocks/handlers";
import { server } from "./setup";

const VACANCIES_URL = "*/api/v1/vacancies";
const SOURCES_URL = "*/api/v1/vacancy-sources";
const LIST_KEY = "jobbi:inbox:listCollapsed";
const SOURCES_KEY = "jobbi:inbox:sourcesCollapsed";

function getToggle(section: "Vacancies" | "Sources", action: "Hide" | "Show"): HTMLElement {
  return screen.getByRole("button", { name: `${action} ${section}` });
}

/** The element the toggle's aria-controls points at. */
function getControlledRegion(toggle: HTMLElement): HTMLElement {
  const id = toggle.getAttribute("aria-controls");
  expect(id).toBeTruthy();
  const region = document.getElementById(id!);
  expect(region).not.toBeNull();
  return region!;
}

async function waitForSources(): Promise<void> {
  await waitFor(() => expect(screen.queryByText("Loading sources…")).not.toBeInTheDocument());
}

/** One card ("Senior React Developer") for every list request. */
function serveOneCard(): void {
  server.use(
    http.get(VACANCIES_URL, () => HttpResponse.json({ ...mockVacancyPageEmpty, items: [mockVacancy], total: 1 })),
  );
}

describe("Inbox collapsible sections (backlog #9)", () => {
  beforeEach(() => {
    serveOneCard();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("starts with both sections expanded", async () => {
    renderWithProviders(<InboxPage />);
    await waitForSources();

    for (const section of ["Vacancies", "Sources"] as const) {
      const toggle = getToggle(section, "Hide");
      expect(toggle).toHaveAttribute("aria-expanded", "true");
      expect(getControlledRegion(toggle)).not.toHaveAttribute("hidden");
    }
    expect(screen.getByRole("combobox", { name: "Source" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Add a channel, job board or page" })).toBeInTheDocument();
  });

  it("hides and shows the Sources panel, keeping its heading and focus on the toggle", async () => {
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForSources();

    const toggle = getToggle("Sources", "Hide");
    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveAccessibleName("Show Sources");
    expect(toggle).toHaveFocus();
    expect(getControlledRegion(toggle)).toHaveAttribute("hidden");
    expect(screen.getByRole("heading", { level: 2, name: "Sources" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Add a channel, job board or page" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Search description" })).not.toBeInTheDocument();
    // The Inbox list is untouched
    expect(screen.getByRole("combobox", { name: "Source" })).toBeInTheDocument();

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle).toHaveAccessibleName("Hide Sources");
    expect(toggle).toHaveFocus();
    expect(screen.getByRole("textbox", { name: "Add a channel, job board or page" })).toBeInTheDocument();
  });

  it("hides and shows the Inbox list (with its filters) from the keyboard", async () => {
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await screen.findByRole("heading", { name: "Senior React Developer" });

    const toggle = getToggle("Vacancies", "Hide");
    toggle.focus();
    await user.keyboard("{Enter}");

    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveAccessibleName("Show Vacancies");
    expect(toggle).toHaveFocus();
    expect(screen.getByRole("heading", { level: 2, name: "Vacancies" })).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Source" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Senior React Developer" })).not.toBeInTheDocument();
    // Sources stays open
    expect(screen.getByRole("textbox", { name: "Add a channel, job board or page" })).toBeInTheDocument();

    await user.keyboard(" ");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle).toHaveFocus();
    expect(screen.getByRole("heading", { name: "Senior React Developer" })).toBeInTheDocument();
  });

  it("remembers each section's choice across remounts", async () => {
    const user = userEvent.setup();
    const first = renderWithProviders(<InboxPage />);
    await waitForSources();
    await user.click(getToggle("Sources", "Hide"));
    expect(localStorage.getItem(SOURCES_KEY)).toBe("true");
    expect(localStorage.getItem(LIST_KEY)).toBeNull();
    first.unmount();

    const second = renderWithProviders(<InboxPage />);
    await waitForSources();
    expect(getToggle("Sources", "Show")).toHaveAttribute("aria-expanded", "false");
    expect(getToggle("Vacancies", "Hide")).toHaveAttribute("aria-expanded", "true");
    await user.click(getToggle("Vacancies", "Hide"));
    await user.click(getToggle("Sources", "Show"));
    expect(localStorage.getItem(LIST_KEY)).toBe("true");
    expect(localStorage.getItem(SOURCES_KEY)).toBe("false");
    second.unmount();

    renderWithProviders(<InboxPage />);
    await waitForSources();
    expect(getToggle("Vacancies", "Show")).toHaveAttribute("aria-expanded", "false");
    expect(getToggle("Sources", "Hide")).toHaveAttribute("aria-expanded", "true");
  });

  it("ignores a stored value it does not understand", async () => {
    localStorage.setItem(SOURCES_KEY, "maybe");
    renderWithProviders(<InboxPage />);
    await waitForSources();
    expect(getToggle("Sources", "Hide")).toHaveAttribute("aria-expanded", "true");
  });

  it("still works, expanded, when storage throws (private mode / blocked)", async () => {
    const getItem = Storage.prototype.getItem;
    const setItem = Storage.prototype.setItem;
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key: string) {
      if (key.startsWith("jobbi:inbox:")) throw new DOMException("blocked", "SecurityError");
      return getItem.call(this, key);
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (
      this: Storage,
      key: string,
      value: string,
    ) {
      if (key.startsWith("jobbi:inbox:")) throw new DOMException("full", "QuotaExceededError");
      setItem.call(this, key, value);
    });
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForSources();

    expect(getToggle("Vacancies", "Hide")).toHaveAttribute("aria-expanded", "true");
    const toggle = getToggle("Sources", "Hide");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("keeps unsaved drafts and filters across collapse and expand", async () => {
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForSources();
    const addInput = screen.getByRole("textbox", { name: "Add a channel, job board or page" });
    await waitFor(() => expect(addInput).toBeEnabled());
    await user.type(addInput, "@draft_channel");
    const description = screen.getByRole("textbox", { name: "Search description" });
    await waitFor(() => expect(description).toBeEnabled());
    await user.clear(description);
    await user.type(description, "Unsaved draft");
    await user.click(screen.getByRole("radio", { name: "Best fit" }));

    await user.click(getToggle("Sources", "Hide"));
    await user.click(getToggle("Vacancies", "Hide"));
    await user.click(getToggle("Sources", "Show"));
    await user.click(getToggle("Vacancies", "Show"));

    expect(screen.getByRole("textbox", { name: "Add a channel, job board or page" })).toHaveValue("@draft_channel");
    expect(screen.getByRole("textbox", { name: "Search description" })).toHaveValue("Unsaved draft");
    expect(screen.getByRole("radio", { name: "Best fit" })).toHaveAttribute("aria-checked", "true");
  });

  it("keeps the Sources panel feeding the Inbox source filter while it is hidden", async () => {
    localStorage.setItem(SOURCES_KEY, "true");
    server.use(
      http.get(SOURCES_URL, () => HttpResponse.json({ ...mockVacancySourcesEmpty, sources: [mockVacancySource] })),
    );
    renderWithProviders(<InboxPage />);

    const select = screen.getByRole("combobox", { name: "Source" });
    expect(await within(select).findByRole("option", { name: "@frontend_jobs" })).toBeInTheDocument();
    expect(getToggle("Sources", "Show")).toHaveAttribute("aria-expanded", "false");
  });

  it("expands a collapsed Inbox list when opened with ?source=, without saving that", async () => {
    localStorage.setItem(LIST_KEY, "true");
    const first = renderWithProviders(<InboxPage />, { initialEntries: ["/inbox?source=telegram:frontend_jobs"] });

    expect(getToggle("Vacancies", "Hide")).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByRole("heading", { name: "Senior React Developer" })).toBeInTheDocument();
    expect(localStorage.getItem(LIST_KEY)).toBe("true");
    first.unmount();

    renderWithProviders(<InboxPage />, { initialEntries: ["/inbox"] });
    expect(getToggle("Vacancies", "Show")).toHaveAttribute("aria-expanded", "false");
  });

  it("keeps the Inbox list collapsed for an empty ?source=", () => {
    localStorage.setItem(LIST_KEY, "true");
    renderWithProviders(<InboxPage />, { initialEntries: ["/inbox?source="] });
    expect(getToggle("Vacancies", "Show")).toHaveAttribute("aria-expanded", "false");
  });
});
