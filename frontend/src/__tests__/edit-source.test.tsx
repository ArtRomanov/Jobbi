import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { VacancySource } from "@/entities/vacancy-source";
import { InboxPage } from "@/pages/inbox";
import { renderWithProviders } from "./utils";
import { mockVacancySource, mockVacancySourcesEmpty, mockWebPreview, mockWebSource } from "./mocks/handlers";
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

/** Record PATCH / preview bodies and count list requests while the default handlers answer. */
function recordRequests(): {
  patches: unknown[];
  previews: unknown[];
  vacancyLists: () => number;
  sourceLists: () => number;
} {
  const patches: unknown[] = [];
  const previews: unknown[] = [];
  let vacancyLists = 0;
  let sourceLists = 0;
  server.events.on("request:start", ({ request }) => {
    const { pathname } = new URL(request.url);
    if (request.method === "POST" && pathname === "/api/v1/vacancy-sources/preview") {
      void request.clone().json().then((body: unknown) => previews.push(body));
    } else if (request.method === "PATCH" && pathname.startsWith("/api/v1/vacancy-sources/")) {
      void request.clone().json().then((body: unknown) => patches.push(body));
    }
    if (request.method === "GET" && pathname === "/api/v1/vacancies") vacancyLists += 1;
    if (request.method === "GET" && pathname === "/api/v1/vacancy-sources") sourceLists += 1;
  });
  return {
    patches,
    previews,
    vacancyLists: () => vacancyLists,
    sourceLists: () => sourceLists,
  };
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
    // Only the name changed, so focus returns to it
    await waitFor(() => expect(within(dialog).getByLabelText("Name")).toHaveFocus());
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

describe("Edit source: links and patterns", () => {
  const LEASE_ERROR = "This source is being scanned — try again in a moment";
  const VUE_URL = "https://geekjob.ru/vacancies?q=vue";
  const LEVER: VacancySource = {
    ...mockVacancySource,
    id: "src-lever",
    key: "lever:acme",
    kind: "lever",
    display_name: "Acme",
  };

  afterEach(() => {
    server.events.removeAllListeners();
    vi.useRealTimers();
  });

  it("prefills the link per kind; only web pages have 'Job link contains'", async () => {
    serveSources([TELEGRAM, LEVER, { ...WEB, job_link_contains: "/vacancy/" }]);
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    let dialog = await openEdit(user, "@frontend_jobs");
    expect(within(dialog).getByLabelText("Link")).toHaveValue("@frontend_jobs");
    expect(within(dialog).queryByLabelText(/Job link contains/)).not.toBeInTheDocument();
    await user.keyboard("{Escape}");

    dialog = await openEdit(user, "Acme");
    expect(within(dialog).getByLabelText("Link")).toHaveValue("https://jobs.lever.co/acme");
    await user.keyboard("{Escape}");

    dialog = await openEdit(user, "Geekjob React");
    expect(within(dialog).getByLabelText("Link")).toHaveValue(mockWebSource.url);
    expect(within(dialog).getByLabelText("Job link contains (optional)")).toHaveValue("/vacancy/");
  });

  it("web pattern edit: preview with source_id, then Save updates the same row", async () => {
    serveSources([WEB]);
    const requests = recordRequests();
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    const dialog = await openEdit(user, "Geekjob React");
    await user.type(within(dialog).getByLabelText("Job link contains (optional)"), "/vacancy/");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(await within(dialog).findByRole("heading", { name: "Found 7 vacancies" })).toBeInTheDocument();
    expect(within(dialog).getByText(mockWebPreview.titles[0] ?? "")).toBeInTheDocument();
    expect(requests.previews).toEqual([
      { input: mockWebSource.url, job_link_contains: "/vacancy/", source_id: "src-web" },
    ]);
    // The preview starts from the dialog's drafts
    expect(within(dialog).getByRole("textbox", { name: "Job link contains (optional)" })).toHaveValue("/vacancy/");
    expect(within(dialog).getByRole("textbox", { name: "Name (optional)" })).toHaveValue("Geekjob React");
    expect(requests.patches).toEqual([]);

    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(requests.patches).toEqual([
      { input: mockWebSource.url, job_link_contains: "/vacancy/", name: "Geekjob React" },
    ]);
    expect(screen.getAllByRole("button", { name: /^Edit / })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Edit Geekjob React" })).toHaveFocus();
  });

  it("web URL edit: shows the preview, Re-check works, then saves the new link", async () => {
    serveSources([WEB]);
    const requests = recordRequests();
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    const dialog = await openEdit(user, "Geekjob React");
    const link = within(dialog).getByLabelText("Link");
    await user.clear(link);
    await user.type(link, VUE_URL);
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(await within(dialog).findByText(`Link: ${VUE_URL}`)).toBeInTheDocument();
    await user.type(within(dialog).getByRole("textbox", { name: "Job link contains (optional)" }), "/job/");
    await user.click(within(dialog).getByRole("button", { name: "Re-check" }));
    await waitFor(() => expect(requests.previews).toHaveLength(2));
    expect(requests.previews[1]).toEqual({ input: VUE_URL, job_link_contains: "/job/", source_id: "src-web" });

    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(requests.patches).toEqual([{ input: VUE_URL, job_link_contains: "/job/", name: "Geekjob React" }]);
  });

  it("Cancel in the preview goes back to the form with the drafts kept", async () => {
    serveSources([WEB]);
    const requests = recordRequests();
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    const dialog = await openEdit(user, "Geekjob React");
    const link = within(dialog).getByLabelText("Link");
    await user.clear(link);
    await user.type(link, VUE_URL);
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await within(dialog).findByRole("heading", { name: "Found 7 vacancies" });

    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(within(dialog).queryByRole("heading", { name: "Found 7 vacancies" })).not.toBeInTheDocument();
    await waitFor(() => expect(within(dialog).getByLabelText("Link")).toHaveFocus());
    expect(within(dialog).getByLabelText("Link")).toHaveValue(VUE_URL);
    expect(requests.patches).toEqual([]);
  });

  it("Telegram link change replaces the row and the old name shows as '(removed)'", async () => {
    let isReplaced = false;
    server.use(
      http.get(SOURCES_URL, () =>
        HttpResponse.json({
          ...mockVacancySourcesEmpty,
          sources: [TELEGRAM],
          removed_sources: isReplaced ? [{ key: "telegram:frontend_jobs", label: "@frontend_jobs" }] : [],
        }),
      ),
      http.patch(SOURCE_URL, () => {
        isReplaced = true;
        return HttpResponse.json({
          ...TELEGRAM,
          id: "src-vue_jobs",
          key: "telegram:vue_jobs",
          display_name: "@vue_jobs",
          scanning: true,
          editable: false,
        });
      }),
    );
    const requests = recordRequests();
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await screen.findByRole("button", { name: "Edit @frontend_jobs" });
    const listsBefore = requests.sourceLists();

    const dialog = await openEdit(user, "@frontend_jobs");
    const link = within(dialog).getByLabelText("Link");
    await user.clear(link);
    await user.type(link, "@vue_jobs");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    // Non-web: no preview UI, PATCHed right away
    expect(requests.previews).toEqual([{ input: "@vue_jobs", job_link_contains: null, source_id: "src-1" }]);
    expect(requests.patches).toEqual([{ input: "@vue_jobs", name: null }]);
    expect(screen.queryByRole("button", { name: "Edit @frontend_jobs" })).not.toBeInTheDocument();
    const newEdit = screen.getByRole("button", { name: "Edit @vue_jobs" });
    expect(newEdit).toHaveAttribute("aria-disabled", "true");
    // The new row starts its first scan
    expect(newEdit.closest("li")).toHaveTextContent("Telegram · Scanning…");
    await waitFor(() => expect(requests.sourceLists()).toBeGreaterThan(listsBefore));
    const select = screen.getByRole("combobox", { name: "Source" });
    expect(
      await within(select).findByRole("option", { name: "@frontend_jobs (removed)" }),
    ).toBeInTheDocument();
    // Its Edit stays focusable while it scans (aria-disabled), so focus lands there
    expect(screen.getByRole("button", { name: "Edit @vue_jobs" })).toHaveFocus();
  });

  it("Telegram link change to a source already watched shows the 409 inline", async () => {
    serveSources([TELEGRAM]);
    server.use(
      http.post("*/api/v1/vacancy-sources/preview", () =>
        HttpResponse.json({ detail: "Already in your sources" }, { status: 409 }),
      ),
    );
    const requests = recordRequests();
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    const dialog = await openEdit(user, "@frontend_jobs");
    const link = within(dialog).getByLabelText("Link");
    await user.clear(link);
    await user.type(link, "@vue_jobs");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Already in your sources");
    expect(screen.getByRole("dialog", { name: "Edit source" })).toBeInTheDocument();
    expect(requests.patches).toEqual([]);
    // Focus goes back to the field the user changed
    await waitFor(() => expect(link).toHaveFocus());
  });

  it("kind change: a Lever board replaced with a web page goes through the preview", async () => {
    serveSources([LEVER]);
    server.use(
      http.patch(SOURCE_URL, () =>
        HttpResponse.json({ ...mockWebSource, id: "src-web-2", display_name: "acme.com" }),
      ),
    );
    const requests = recordRequests();
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    const dialog = await openEdit(user, "Acme");
    const link = within(dialog).getByLabelText("Link");
    await user.clear(link);
    await user.type(link, "https://acme.com/careers");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await within(dialog).findByRole("heading", { name: "Found 7 vacancies" });
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(requests.patches).toEqual([
      { input: "https://acme.com/careers", job_link_contains: null, name: null },
    ]);
    expect(screen.queryByRole("button", { name: "Edit Acme" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit acme.com" })).toHaveFocus();
  });

  it("shows the 409 'being scanned' text inline (form and preview)", async () => {
    serveSources([WEB]);
    server.use(http.patch(SOURCE_URL, () => HttpResponse.json({ detail: LEASE_ERROR }, { status: 409 })));
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    const dialog = await openEdit(user, "Geekjob React");
    await user.type(within(dialog).getByLabelText("Name"), "!");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(LEASE_ERROR);

    await user.type(within(dialog).getByLabelText("Job link contains (optional)"), "/vacancy/");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await within(dialog).findByRole("heading", { name: "Found 7 vacancies" });
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(LEASE_ERROR);
    expect(screen.getByRole("dialog", { name: "Edit source" })).toBeInTheDocument();
  });

  it("Edit is aria-disabled while a scan attempt runs and re-enabled by a poll", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"], shouldAdvanceTime: true });
    let isScanning = true;
    server.use(
      http.get(SOURCES_URL, () =>
        HttpResponse.json({
          ...mockVacancySourcesEmpty,
          sources: [{ ...TELEGRAM, scanning: isScanning, editable: !isScanning }],
        }),
      ),
    );
    renderWithProviders(<InboxPage />);

    const edit = await screen.findByRole("button", { name: "Edit @frontend_jobs" });
    // Focusable (not `disabled`) so the reason is announced; clicking does nothing
    expect(edit).toBeEnabled();
    expect(edit).toHaveAttribute("aria-disabled", "true");
    expect(edit).toHaveAccessibleDescription("Scanning — try again in a moment");
    edit.focus();
    expect(edit).toHaveFocus();
    act(() => edit.click());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    isScanning = false;
    await act(() => vi.advanceTimersByTimeAsync(5000));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Edit @frontend_jobs" })).not.toHaveAttribute("aria-disabled"),
    );
    expect(screen.getByRole("button", { name: "Edit @frontend_jobs" })).not.toHaveAccessibleDescription();
  });

  it("a poll that started before an edit saved does not overwrite the edited row", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"], shouldAdvanceTime: true });
    // Scanning keeps the 5 s poll running; the old link is broken
    const stale: VacancySource = { ...WEB, scanning: true, unavailable: true, last_error: "Page not found" };
    const fixed: VacancySource = { ...WEB, scanning: true, url: VUE_URL };
    const pollGate = createGate();
    let listCalls = 0;
    let isPollStarted = false;
    server.use(
      http.get(SOURCES_URL, async () => {
        listCalls += 1;
        if (listCalls === 2) {
          isPollStarted = true;
          await pollGate.wait;
        }
        return HttpResponse.json({ ...mockVacancySourcesEmpty, sources: [listCalls <= 2 ? stale : fixed] });
      }),
      http.patch(SOURCE_URL, () => HttpResponse.json(fixed)),
    );
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<InboxPage />);
    expect(await screen.findByText("Unavailable — Page not found")).toBeInTheDocument();

    // The poll's GET goes out and is held while the user saves a new link
    await act(() => vi.advanceTimersByTimeAsync(5000));
    await waitFor(() => expect(isPollStarted).toBe(true));
    const dialog = await openEdit(user, "Geekjob React");
    const link = within(dialog).getByLabelText("Link");
    await user.clear(link);
    await user.type(link, VUE_URL);
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await within(dialog).findByRole("heading", { name: "Found 7 vacancies" });
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.queryByText("Unavailable — Page not found")).not.toBeInTheDocument();

    // The stale answer lands after the save: the edited row keeps its copy
    pollGate.open();
    await waitFor(() => expect(listCalls).toBeGreaterThanOrEqual(2));
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(screen.queryByText("Unavailable — Page not found")).not.toBeInTheDocument();
  });

  it("Escape does nothing while a changed link is being checked", async () => {
    serveSources([WEB]);
    const gate = createGate();
    server.use(
      http.post("*/api/v1/vacancy-sources/preview", async () => {
        await gate.wait;
        return HttpResponse.json(mockWebPreview);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    const dialog = await openEdit(user, "Geekjob React");
    const link = within(dialog).getByLabelText("Link");
    await user.clear(link);
    await user.type(link, VUE_URL);
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog", { name: "Edit source" })).toBeInTheDocument();

    gate.open();
    expect(await within(dialog).findByRole("heading", { name: "Found 7 vacancies" })).toBeInTheDocument();
  });

  it("an empty link shows 'Enter a link' and sends nothing", async () => {
    serveSources([TELEGRAM]);
    const requests = recordRequests();
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    const dialog = await openEdit(user, "@frontend_jobs");
    await user.clear(within(dialog).getByLabelText("Link"));
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(await within(dialog).findByText("Enter a link")).toBeInTheDocument();
    expect(requests.previews).toEqual([]);
    expect(requests.patches).toEqual([]);
  });
});
