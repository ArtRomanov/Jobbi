import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { VacancySource } from "@/entities/vacancy-source";
import { InboxPage } from "@/pages/inbox";
import { renderWithProviders } from "./utils";
import { mockVacancySource, mockVacancySourcesEmpty, mockWebSource } from "./mocks/handlers";
import { server } from "./setup";

// Source names also appear as options of the Inbox source filter
const OUTSIDE_SOURCE_FILTER = { ignore: "script, style, option" };

const SOURCES_URL = "*/api/v1/vacancy-sources";
const SOURCE_URL = "*/api/v1/vacancy-sources/:id";

const TELEGRAM: VacancySource = { ...mockVacancySource };
const GREENHOUSE: VacancySource = {
  ...mockVacancySource,
  id: "src-gh",
  key: "greenhouse:acme",
  kind: "greenhouse",
  display_name: "Acme",
};
const WEB: VacancySource = { ...mockWebSource, name_is_custom: true, display_name: "Geekjob React" };

function serveSources(sources: VacancySource[]): void {
  server.use(http.get(SOURCES_URL, () => HttpResponse.json({ ...mockVacancySourcesEmpty, sources })));
}

/** Record PATCH bodies and count vacancy list requests while the default handlers answer. */
function recordRequests(): { patches: unknown[]; vacancyLists: () => number } {
  const patches: unknown[] = [];
  let vacancyLists = 0;
  server.events.on("request:start", ({ request }) => {
    const { pathname } = new URL(request.url);
    if (request.method === "PATCH" && pathname.startsWith("/api/v1/vacancy-sources/")) {
      void request.clone().json().then((body: unknown) => patches.push(body));
    }
    if (request.method === "GET" && pathname === "/api/v1/vacancies") vacancyLists += 1;
  });
  return { patches, vacancyLists: () => vacancyLists };
}

/** A promise the test resolves by hand, to hold an MSW response in flight. */
function createGate(): { wait: Promise<void>; open: () => void } {
  let open = (): void => {};
  const wait = new Promise<void>((resolve) => {
    open = resolve;
  });
  return { wait, open };
}

async function openEdit(user: ReturnType<typeof userEvent.setup>, name: string): Promise<HTMLElement> {
  await user.click(await screen.findByRole("button", { name: `Edit ${name}` }));
  return screen.getByRole("dialog", { name: "Edit source" });
}

describe("Edit source: rename", () => {
  afterEach(() => {
    server.events.removeAllListeners();
  });

  it("shows an Edit button on Telegram, Greenhouse and web page rows", async () => {
    serveSources([TELEGRAM, GREENHOUSE, WEB]);
    renderWithProviders(<InboxPage />);

    expect(await screen.findByRole("button", { name: "Edit @frontend_jobs" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Acme" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Geekjob React" })).toBeInTheDocument();
  });

  it("opens with the current custom name, the hint and the name as placeholder", async () => {
    serveSources([WEB]);
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    const dialog = await openEdit(user, "Geekjob React");
    const field = within(dialog).getByLabelText("Name");
    expect(field).toHaveValue("Geekjob React");
    expect(field).toHaveFocus();
    expect(field).toHaveAttribute("placeholder", "Geekjob React");
    const hint = within(dialog).getByText("Leave empty to use the default name");
    expect(field.getAttribute("aria-describedby")).toContain(hint.id);
  });

  it("a default-named source opens empty with the default name as placeholder", async () => {
    serveSources([TELEGRAM]);
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    const dialog = await openEdit(user, "@frontend_jobs");
    const field = within(dialog).getByLabelText("Name");
    expect(field).toHaveValue("");
    expect(field).toHaveAttribute("placeholder", "@frontend_jobs");
  });

  it("renames: the row shows the new name, the vacancy list refetches, focus returns to Edit", async () => {
    serveSources([TELEGRAM]);
    const requests = recordRequests();
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await screen.findByText("No vacancies yet.");
    const listsBefore = requests.vacancyLists();

    const dialog = await openEdit(user, "@frontend_jobs");
    await user.type(within(dialog).getByLabelText("Name"), "  Frontend jobs  ");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    const name = await screen.findByText("Frontend jobs", OUTSIDE_SOURCE_FILTER);
    expect(name.closest("li")).not.toBeNull();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(requests.patches).toEqual([{ name: "Frontend jobs" }]);
    await waitFor(() => expect(requests.vacancyLists()).toBeGreaterThan(listsBefore));
    // The filter option follows the new name too
    expect(screen.getByRole("option", { name: "Frontend jobs" })).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Edit Frontend jobs" })).toHaveFocus(),
    );
  });

  it("an empty name sends {name: null} and the default name comes back", async () => {
    serveSources([{ ...WEB, id: "src-web" }]);
    const requests = recordRequests();
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    const dialog = await openEdit(user, "Geekjob React");
    await user.clear(within(dialog).getByLabelText("Name"));
    await user.type(within(dialog).getByLabelText("Name"), "   ");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(await screen.findByText("@src-web", OUTSIDE_SOURCE_FILTER)).toBeInTheDocument();
    expect(requests.patches).toEqual([{ name: null }]);
  });

  it("a 101-character name shows a validation message and sends nothing", async () => {
    serveSources([TELEGRAM]);
    const requests = recordRequests();
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    const dialog = await openEdit(user, "@frontend_jobs");
    const field = within(dialog).getByLabelText("Name");
    await user.click(field);
    await user.paste("a".repeat(101));
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(await within(dialog).findByText("Use up to 100 characters")).toBeInTheDocument();
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(requests.patches).toEqual([]);
  });

  it("shows a server error inline and keeps the dialog open", async () => {
    serveSources([TELEGRAM]);
    server.use(
      http.patch(SOURCE_URL, () =>
        HttpResponse.json({ detail: "Name can be up to 100 characters" }, { status: 400 }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    const dialog = await openEdit(user, "@frontend_jobs");
    await user.type(within(dialog).getByLabelText("Name"), "x");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Name can be up to 100 characters",
    );
    expect(screen.getByRole("dialog", { name: "Edit source" })).toBeInTheDocument();
  });

  it("Escape closes the dialog without saving and focus returns to Edit", async () => {
    serveSources([TELEGRAM]);
    const requests = recordRequests();
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    await openEdit(user, "@frontend_jobs");
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit @frontend_jobs" })).toHaveFocus();
    expect(requests.patches).toEqual([]);
  });

  it("Escape does nothing while saving", async () => {
    serveSources([TELEGRAM]);
    const gate = createGate();
    server.use(
      http.patch(SOURCE_URL, async () => {
        await gate.wait;
        return HttpResponse.json({ ...TELEGRAM, display_name: "Renamed", name_is_custom: true });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    const dialog = await openEdit(user, "@frontend_jobs");
    await user.type(within(dialog).getByLabelText("Name"), "Renamed");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog", { name: "Edit source" })).toBeInTheDocument();

    gate.open();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByText("Renamed", OUTSIDE_SOURCE_FILTER)).toBeInTheDocument();
  });
});
