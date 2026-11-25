import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { InboxPage } from "@/pages/inbox";
import { renderWithProviders } from "./utils";
import { mockVacancySourcesEmpty, mockWebPreview, mockWebSource } from "./mocks/handlers";
import { server } from "./setup";

// Source names also appear as options of the Inbox source filter
const OUTSIDE_SOURCE_FILTER = { ignore: "script, style, option" };

const SOURCES_URL = "*/api/v1/vacancy-sources";
const PREVIEW_URL = "*/api/v1/vacancy-sources/preview";
const PAGE_LINK = "https://geekjob.ru/vacancies?q=react";
const NO_VACANCIES = "No vacancies found on this page. Check the link or set 'Job link contains'.";

function getInput(): HTMLElement {
  return screen.getByLabelText("Add a channel, job board or page");
}

async function waitForList(): Promise<void> {
  await waitFor(() => expect(screen.queryByText("Loading sources…")).not.toBeInTheDocument());
}

/** Record every preview / create request body while the default handlers answer. */
function recordBodies(): { previews: unknown[]; creates: unknown[] } {
  const previews: unknown[] = [];
  const creates: unknown[] = [];
  server.events.on("request:start", ({ request }) => {
    if (request.method !== "POST") return;
    const { pathname } = new URL(request.url);
    const target = pathname.endsWith("/vacancy-sources/preview")
      ? previews
      : pathname.endsWith("/vacancy-sources")
        ? creates
        : null;
    if (target) void request.clone().json().then((body: unknown) => target.push(body));
  });
  return { previews, creates };
}

/** A promise the test resolves by hand, to hold an MSW response in flight. */
function createGate(): { wait: Promise<void>; open: () => void } {
  let open = (): void => {};
  const wait = new Promise<void>((resolve) => {
    open = resolve;
  });
  return { wait, open };
}

async function openPreview(user: ReturnType<typeof userEvent.setup>): Promise<HTMLElement> {
  await user.type(getInput(), `${PAGE_LINK}{Enter}`);
  const heading = await screen.findByRole("heading", { name: "Found 7 vacancies" });
  return heading.closest("section") as HTMLElement;
}

describe("Web page source: add with preview", () => {
  afterEach(() => {
    server.events.removeAllListeners();
  });

  it("always shows the sort-by-newest hint under the input", async () => {
    renderWithProviders(<InboxPage />);
    await waitForList();

    const hint = screen.getByText("Sort the page by newest first before copying the link");
    expect(getInput().getAttribute("aria-describedby")).toContain(hint.id);
  });

  it("previews a web page: count, the 5 titles in order, focus on the heading, nothing saved", async () => {
    const bodies = recordBodies();
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    const preview = await openPreview(user);

    const titles = within(preview)
      .getAllByRole("listitem")
      .map((item) => item.textContent);
    expect(titles).toEqual(mockWebPreview.titles);
    expect(screen.getByRole("heading", { name: "Found 7 vacancies" })).toHaveFocus();
    expect(within(preview).getByLabelText("Name (optional)")).toHaveAttribute(
      "placeholder",
      "geekjob.ru",
    );
    expect(preview.querySelector("[aria-live='polite']")).not.toBeNull();
    await waitFor(() => expect(bodies.previews).toEqual([{ input: PAGE_LINK }]));
    expect(bodies.creates).toEqual([]);
    expect(screen.getByText("You are not watching any sources yet.")).toBeInTheDocument();
  });

  it("re-checks with the 'Job link contains' pattern and shows the new result", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(PREVIEW_URL, async ({ request }) => {
        const body = (await request.json()) as { job_link_contains?: string | null };
        bodies.push(body);
        return HttpResponse.json(
          body.job_link_contains
            ? { ...mockWebPreview, found_count: 1, titles: ["Only React"] }
            : mockWebPreview,
        );
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    const preview = await openPreview(user);
    await user.type(within(preview).getByLabelText("Job link contains (optional)"), " /vacancy/ ");
    await user.click(within(preview).getByRole("button", { name: "Re-check" }));

    expect(await screen.findByRole("heading", { name: "Found 1 vacancy" })).toBeInTheDocument();
    expect(screen.getByText("Only React")).toBeInTheDocument();
    expect(bodies).toEqual([
      { input: PAGE_LINK },
      { input: PAGE_LINK, job_link_contains: "/vacancy/" },
    ]);
    // The pattern stays in the field for Save
    expect(screen.getByLabelText("Job link contains (optional)")).toHaveValue(" /vacancy/ ");
  });

  it("saves with the pattern and name: the row shows 'Web page · Watching since', the form resets", async () => {
    const bodies = recordBodies();
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    const preview = await openPreview(user);
    await user.type(within(preview).getByLabelText("Job link contains (optional)"), "/vacancy/");
    await user.type(within(preview).getByLabelText("Name (optional)"), "Geekjob — React");
    await user.click(within(preview).getByRole("button", { name: "Save" }));

    const name = await screen.findByText("Geekjob — React", OUTSIDE_SOURCE_FILTER);
    const row = name.closest("li") as HTMLElement;
    expect(within(row).getByText("Web page · Watching since just now")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /^Found/ })).not.toBeInTheDocument();
    expect(getInput()).toHaveValue("");
    await waitFor(() => expect(getInput()).toHaveFocus());
    expect(bodies.creates).toEqual([
      { input: PAGE_LINK, job_link_contains: "/vacancy/", name: "Geekjob — React" },
    ]);
  });

  it("sends a blank name and pattern as null (server default name)", async () => {
    const bodies = recordBodies();
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    const preview = await openPreview(user);
    await user.type(within(preview).getByLabelText("Name (optional)"), "   ");
    await user.click(within(preview).getByRole("button", { name: "Save" }));

    expect(await screen.findByText("geekjob.ru", OUTSIDE_SOURCE_FILTER)).toBeInTheDocument();
    expect(bodies.creates).toEqual([{ input: PAGE_LINK, job_link_contains: null, name: null }]);
  });

  it("Cancel closes the preview, keeps the input and focuses it", async () => {
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    const preview = await openPreview(user);
    await user.click(within(preview).getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("heading", { name: /^Found/ })).not.toBeInTheDocument();
    expect(getInput()).toHaveValue(PAGE_LINK);
    expect(getInput()).toHaveFocus();
    expect(screen.getByText("You are not watching any sources yet.")).toBeInTheDocument();
  });

  it("adds a non-web kind right away without the preview UI", async () => {
    const bodies = recordBodies();
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    await user.type(getInput(), "@react_jobs{Enter}");

    expect(await screen.findByText("@react_jobs", OUTSIDE_SOURCE_FILTER)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /^Found/ })).not.toBeInTheDocument();
    expect(bodies.previews).toEqual([{ input: "@react_jobs" }]);
    expect(bodies.creates).toEqual([{ input: "@react_jobs" }]);
  });

  it.each([
    [400, "This link can't be used"],
    [400, "Could not open this page"],
    [400, NO_VACANCIES],
    [409, "Already in your sources"],
    [400, "You can watch up to 50 sources"],
  ])("shows the %i preview error %s inline under the input", async (status, detail) => {
    server.use(http.post(PREVIEW_URL, () => HttpResponse.json({ detail }, { status })));
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    await user.type(getInput(), `${PAGE_LINK}{Enter}`);

    expect(await screen.findByRole("alert")).toHaveTextContent(detail);
    expect(getInput()).toHaveAttribute("aria-invalid", "true");
    expect(getInput()).toHaveValue(PAGE_LINK);
    expect(getInput()).toHaveFocus();
    expect(screen.queryByRole("heading", { name: /^Found/ })).not.toBeInTheDocument();
  });

  it("shows a re-check error inside the preview and keeps the last result", async () => {
    server.use(
      http.post(PREVIEW_URL, async ({ request }) => {
        const body = (await request.json()) as { job_link_contains?: string | null };
        return body.job_link_contains
          ? HttpResponse.json({ detail: NO_VACANCIES }, { status: 400 })
          : HttpResponse.json(mockWebPreview);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    const preview = await openPreview(user);
    await user.type(within(preview).getByLabelText("Job link contains (optional)"), "/nope/{Enter}");

    expect(await within(preview).findByRole("alert")).toHaveTextContent(NO_VACANCIES);
    expect(screen.getByRole("heading", { name: "Found 7 vacancies" })).toBeInTheDocument();
    expect(getInput()).not.toHaveAttribute("aria-invalid");
  });

  it("shows a save error inside the preview and adds nothing", async () => {
    server.use(
      http.post(SOURCES_URL, () =>
        HttpResponse.json({ detail: "Already in your sources" }, { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    const preview = await openPreview(user);
    await user.click(within(preview).getByRole("button", { name: "Save" }));

    expect(await within(preview).findByRole("alert")).toHaveTextContent("Already in your sources");
    expect(screen.getByText("You are not watching any sources yet.")).toBeInTheDocument();
    expect(getInput()).toHaveValue(PAGE_LINK);
  });

  it("sends one preview when the add form is submitted twice in one tick; input read-only meanwhile", async () => {
    const gate = createGate();
    let previews = 0;
    server.use(
      http.post(PREVIEW_URL, async () => {
        previews += 1;
        await gate.wait;
        return HttpResponse.json(mockWebPreview);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    await user.type(getInput(), PAGE_LINK);
    const form = getInput().closest("form") as HTMLFormElement;
    // Both submits run before React re-renders, so only the busy ref can block the second
    act(() => {
      form.requestSubmit();
      form.requestSubmit();
    });
    expect(getInput()).toHaveAttribute("readonly");
    expect(screen.getByRole("button", { name: "Add" })).toHaveAttribute("aria-busy", "true");
    gate.open();

    expect(await screen.findByRole("heading", { name: "Found 7 vacancies" })).toBeInTheDocument();
    expect(previews).toBe(1);
    expect(getInput()).not.toHaveAttribute("readonly");
  });

  it("sends one create when Save is submitted twice in one tick", async () => {
    const gate = createGate();
    let creates = 0;
    server.use(
      http.post(SOURCES_URL, async () => {
        creates += 1;
        await gate.wait;
        return HttpResponse.json({ ...mockWebSource, id: "once" }, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    const preview = await openPreview(user);
    const form = within(preview).getByRole("button", { name: "Save" }).closest("form") as HTMLFormElement;
    // Both submits run before React re-renders, so only the busy ref can block the second
    act(() => {
      form.requestSubmit();
      form.requestSubmit();
    });
    gate.open();

    expect(await screen.findByText("geekjob.ru", OUTSIDE_SOURCE_FILTER)).toBeInTheDocument();
    expect(creates).toBe(1);
  });

  it("refocuses Save after a failed save", async () => {
    server.use(
      http.post(SOURCES_URL, () =>
        HttpResponse.json({ detail: "Already in your sources" }, { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    const preview = await openPreview(user);
    const save = within(preview).getByRole("button", { name: "Save" });
    await user.click(save);

    expect(await within(preview).findByRole("alert")).toHaveTextContent("Already in your sources");
    await waitFor(() => expect(save).toHaveFocus());
  });

  it("keeps focus in 'Job link contains' after Enter re-checks", async () => {
    const bodies = recordBodies();
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    const preview = await openPreview(user);
    const pattern = within(preview).getByLabelText("Job link contains (optional)");
    await user.type(pattern, "/vacancy/{Enter}");

    await waitFor(() => expect(bodies.previews).toHaveLength(2));
    await waitFor(() => expect(pattern).not.toHaveAttribute("readonly"));
    expect(pattern).toHaveFocus();
  });

  it("closes an open preview when the add input is edited", async () => {
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    await openPreview(user);
    await user.type(getInput(), "x");

    expect(screen.queryByRole("heading", { name: /^Found/ })).not.toBeInTheDocument();
    expect(getInput()).toHaveValue(`${PAGE_LINK}x`);
  });

  it("shows 'Last checked' for a web source checked after it started watching", async () => {
    server.use(
      http.get(SOURCES_URL, () =>
        HttpResponse.json({
          ...mockVacancySourcesEmpty,
          sources: [
            mockWebSource,
            {
              ...mockWebSource,
              id: "checked",
              display_name: "ingamejob.com",
              last_checked_at: new Date().toISOString(),
            },
          ],
        }),
      ),
    );
    renderWithProviders(<InboxPage />);
    await waitForList();

    const watching = screen.getByText("geekjob.ru", OUTSIDE_SOURCE_FILTER).closest("li") as HTMLElement;
    expect(within(watching).getByText(/^Web page · Watching since /)).toBeInTheDocument();
    const checked = screen
      .getByText("ingamejob.com", OUTSIDE_SOURCE_FILTER)
      .closest("li") as HTMLElement;
    expect(within(checked).getByText("Web page · Last checked just now")).toBeInTheDocument();
  });
});

describe("Web page source: ATS hint in the preview", () => {
  const BOARD_LINK = "https://job-boards.greenhouse.io/wrike";
  const BOARD_TEXT = "Board: job-boards.greenhouse.io/wrike";
  const ADD_BOARD_NAME = "Add the board job-boards.greenhouse.io/wrike";
  const HINT_TEXT =
    "This page uses Greenhouse — add the board instead for full job texts and dates";

  function mockHintPreview(): void {
    server.use(
      http.post(PREVIEW_URL, () =>
        HttpResponse.json({
          ...mockWebPreview,
          ats_hint: { kind: "greenhouse", input: BOARD_LINK, label: "Greenhouse" },
        }),
      ),
    );
  }

  afterEach(() => {
    server.events.removeAllListeners();
  });

  it("shows the hint with the service name and 'Add the board'", async () => {
    mockHintPreview();
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    const preview = await openPreview(user);

    expect(within(preview).getByText(HINT_TEXT)).toBeInTheDocument();
    // The board is named as plain text, not a link
    expect(within(preview).getByText(BOARD_TEXT)).toBeInTheDocument();
    expect(within(preview).queryByRole("link", { name: /greenhouse/ })).not.toBeInTheDocument();
    expect(within(preview).getByRole("button", { name: ADD_BOARD_NAME })).toBeEnabled();
    // The page itself can still be saved
    expect(within(preview).getByRole("button", { name: "Save" })).toBeEnabled();
  });

  it("shows no hint when the page links to no board", async () => {
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    const preview = await openPreview(user);

    expect(within(preview).queryByText(/This page uses/)).not.toBeInTheDocument();
    expect(within(preview).queryByRole("button", { name: /^Add the board/ })).not.toBeInTheDocument();
    expect(within(preview).queryByText(/^Board:/)).not.toBeInTheDocument();
  });

  it("'Add the board' adds the board, closes the preview, clears and focuses the input", async () => {
    mockHintPreview();
    const creates: unknown[] = [];
    server.use(
      http.post(SOURCES_URL, async ({ request }) => {
        creates.push(await request.json());
        return HttpResponse.json(
          {
            ...mockWebSource,
            id: "src-wrike",
            key: "greenhouse:wrike",
            kind: "greenhouse",
            display_name: "Wrike",
            url: BOARD_LINK,
            watching_since: null,
            last_checked_at: null,
            scanning: true,
          },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    const preview = await openPreview(user);
    await user.click(within(preview).getByRole("button", { name: ADD_BOARD_NAME }));

    expect(await screen.findByText("Wrike", OUTSIDE_SOURCE_FILTER)).toBeInTheDocument();
    expect(creates).toEqual([{ input: BOARD_LINK }]);
    expect(screen.queryByRole("heading", { name: /^Found/ })).not.toBeInTheDocument();
    expect(getInput()).toHaveValue("");
    await waitFor(() => expect(getInput()).toHaveFocus());
  });

  it("shows a board add error inside the preview and keeps it open", async () => {
    mockHintPreview();
    server.use(
      http.post(SOURCES_URL, () =>
        HttpResponse.json({ detail: "Already in your sources" }, { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    const preview = await openPreview(user);
    const button = within(preview).getByRole("button", { name: ADD_BOARD_NAME });
    await user.click(button);

    expect(await within(preview).findByRole("alert")).toHaveTextContent("Already in your sources");
    expect(screen.getByRole("heading", { name: "Found 7 vacancies" })).toBeInTheDocument();
    expect(screen.getByText("You are not watching any sources yet.")).toBeInTheDocument();
    expect(getInput()).toHaveValue(PAGE_LINK);
    await waitFor(() => expect(button).toHaveFocus());
  });

  describe("page with no job links but a board", () => {
    /** Zero jobs + hint without a pattern; a pattern re-check finds jobs. */
    function mockZeroJobsHintPreview(): void {
      server.use(
        http.post(PREVIEW_URL, async ({ request }) => {
          const body = (await request.json()) as { job_link_contains?: string | null };
          const hint = { kind: "greenhouse", input: BOARD_LINK, label: "Greenhouse" };
          return HttpResponse.json(
            body.job_link_contains
              ? { ...mockWebPreview, found_count: 2, titles: ["A", "B"], ats_hint: hint }
              : { ...mockWebPreview, found_count: 0, titles: [], ats_hint: hint },
          );
        }),
      );
    }

    async function openZeroPreview(user: ReturnType<typeof userEvent.setup>): Promise<HTMLElement> {
      await user.type(getInput(), `${PAGE_LINK}{Enter}`);
      const heading = await screen.findByRole("heading", { name: NO_VACANCIES });
      return heading.closest("section") as HTMLElement;
    }

    it("shows the no-vacancies text, the hint and no enabled Save", async () => {
      mockZeroJobsHintPreview();
      const user = userEvent.setup();
      renderWithProviders(<InboxPage />);
      await waitForList();

      const preview = await openZeroPreview(user);

      expect(within(preview).queryByText(/^Found/)).not.toBeInTheDocument();
      expect(within(preview).queryAllByRole("listitem")).toHaveLength(0);
      expect(within(preview).queryByRole("alert")).not.toBeInTheDocument();
      expect(within(preview).getByText(HINT_TEXT)).toBeInTheDocument();
      expect(within(preview).getByRole("button", { name: ADD_BOARD_NAME })).toBeEnabled();
      expect(within(preview).getByRole("button", { name: "Save" })).toBeDisabled();
      expect(within(preview).getByRole("button", { name: "Re-check" })).toBeEnabled();
    });

    it("'Add the board' works from the no-vacancies state", async () => {
      mockZeroJobsHintPreview();
      const creates: unknown[] = [];
      server.use(
        http.post(SOURCES_URL, async ({ request }) => {
          creates.push(await request.json());
          return HttpResponse.json(
            {
              ...mockWebSource,
              id: "src-wrike",
              key: "greenhouse:wrike",
              kind: "greenhouse",
              display_name: "Wrike",
              url: BOARD_LINK,
              watching_since: null,
              last_checked_at: null,
              scanning: true,
            },
            { status: 201 },
          );
        }),
      );
      const user = userEvent.setup();
      renderWithProviders(<InboxPage />);
      await waitForList();

      const preview = await openZeroPreview(user);
      await user.click(within(preview).getByRole("button", { name: ADD_BOARD_NAME }));

      expect(await screen.findByText("Wrike", OUTSIDE_SOURCE_FILTER)).toBeInTheDocument();
      expect(creates).toEqual([{ input: BOARD_LINK }]);
      expect(screen.queryByRole("heading", { name: NO_VACANCIES })).not.toBeInTheDocument();
      await waitFor(() => expect(getInput()).toHaveFocus());
    });

    it("a re-check that finds jobs shows them and re-enables Save", async () => {
      mockZeroJobsHintPreview();
      const user = userEvent.setup();
      renderWithProviders(<InboxPage />);
      await waitForList();

      const preview = await openZeroPreview(user);
      await user.type(within(preview).getByLabelText("Job link contains (optional)"), "/jobs/");
      await user.click(within(preview).getByRole("button", { name: "Re-check" }));

      expect(await screen.findByRole("heading", { name: "Found 2 vacancies" })).toBeInTheDocument();
      expect(within(preview).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
        "A",
        "B",
      ]);
      expect(within(preview).getByRole("button", { name: "Save" })).toBeEnabled();
    });
  });
});
