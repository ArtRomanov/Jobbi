import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { VacancySource } from "@/entities/vacancy-source";
import { InboxPage } from "@/pages/inbox";
import { renderWithProviders } from "./utils";
import { mockVacancySource, mockVacancySourcesEmpty } from "./mocks/handlers";
import { server } from "./setup";

// Source names also appear as options of the Inbox source filter
const OUTSIDE_SOURCE_FILTER = { ignore: "script, style, option" };

const SOURCES_URL = "*/api/v1/vacancy-sources";
const SOURCE_URL = "*/api/v1/vacancy-sources/:id";

function serveSources(sources: VacancySource[]): void {
  server.use(http.get(SOURCES_URL, () => HttpResponse.json({ ...mockVacancySourcesEmpty, sources })));
}

/** A promise the test resolves by hand, to hold an MSW response in flight. */
function createGate(): { wait: Promise<void>; open: () => void } {
  let open = (): void => {};
  const wait = new Promise<void>((resolve) => {
    open = resolve;
  });
  return { wait, open };
}

function getInput(): HTMLElement {
  return screen.getByLabelText("Add a channel, job board or page");
}

async function waitForList(): Promise<void> {
  await waitFor(() => expect(screen.queryByText("Loading sources…")).not.toBeInTheDocument());
}

describe("InboxPage", () => {
  it("renders the heading, empty state and Sources panel", async () => {
    renderWithProviders(<InboxPage />);

    expect(screen.getByRole("heading", { level: 1, name: "Inbox" })).toBeInTheDocument();
    expect(await screen.findByText("No vacancies yet.")).toBeInTheDocument();
    expect(
      screen.getByText("Add channels or companies and describe what you're looking for in Sources."),
    ).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Sources" })).toBeInTheDocument();
    expect(await screen.findByText("You are not watching any sources yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
  });

  it("lists sources with kind, scanning and unavailable states", async () => {
    serveSources([
      { ...mockVacancySource, id: "a", display_name: "@scanning_one", scanning: true },
      {
        ...mockVacancySource,
        id: "b",
        display_name: "@broken_one",
        unavailable: true,
        last_error: "Channel is private or deleted",
      },
    ]);
    renderWithProviders(<InboxPage />);

    const list = await screen.findByRole("list", { name: "Watched sources" });
    const [scanning, broken, ...rest] = within(list).getAllByRole("listitem");
    expect(rest).toHaveLength(0);
    expect(within(scanning!).getByText("@scanning_one")).toBeInTheDocument();
    expect(within(scanning!).getByText("Telegram · Scanning…")).toBeInTheDocument();
    expect(
      within(broken!).getByText("Unavailable — Channel is private or deleted"),
    ).toBeInTheDocument();
  });

  it("shows the Teamtailor kind label for a Teamtailor board", async () => {
    serveSources([
      {
        ...mockVacancySource,
        id: "tt",
        kind: "teamtailor",
        key: "teamtailor:approvalmax",
        display_name: "ApprovalMax",
      },
    ]);
    renderWithProviders(<InboxPage />);

    const list = await screen.findByRole("list", { name: "Watched sources" });
    const [row] = within(list).getAllByRole("listitem");
    expect(within(row!).getByText("ApprovalMax")).toBeInTheDocument();
    expect(within(row!).getByText(/^Teamtailor/)).toBeInTheDocument();
  });

  it("adds a channel on Enter: it appears in the list and the input is cleared", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(SOURCES_URL, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(
          { ...mockVacancySource, id: "new", display_name: "@react_jobs" },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    await user.type(getInput(), "  t.me/react_jobs  {Enter}");

    expect(await screen.findByText("@react_jobs", OUTSIDE_SOURCE_FILTER)).toBeInTheDocument();
    expect(bodies).toEqual([{ input: "t.me/react_jobs" }]);
    expect(getInput()).toHaveValue("");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it.each([
    [400, "Enter a Telegram channel as @name or a t.me/name link"],
    [400, "This channel is not public or does not exist"],
    [400, "Could not reach Telegram. Please try again."],
    [400, "You can watch up to 30 sources"],
    [409, "Already in your sources"],
  ])("shows the %i error %s inline and keeps the input", async (status, detail) => {
    server.use(http.post(SOURCES_URL, () => HttpResponse.json({ detail }, { status })));
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    await user.type(getInput(), "@some_channel");
    await user.click(screen.getByRole("button", { name: "Add" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(detail);
    expect(getInput()).toHaveValue("@some_channel");
    expect(getInput()).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("You are not watching any sources yet.")).toBeInTheDocument();
  });

  it("clears the inline error when the input changes", async () => {
    server.use(
      http.post(SOURCES_URL, () =>
        HttpResponse.json({ detail: "Already in your sources" }, { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    await user.type(getInput(), "@dup_channel{Enter}");
    expect(await screen.findByRole("alert")).toBeInTheDocument();

    await user.type(getInput(), "x");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("removes a source", async () => {
    const deleted: string[] = [];
    serveSources([
      { ...mockVacancySource, id: "keep", display_name: "@keep_me" },
      { ...mockVacancySource, id: "gone", display_name: "@remove_me" },
    ]);
    server.use(
      http.delete(SOURCE_URL, ({ params }) => {
        deleted.push(params.id as string);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    await user.click(await screen.findByRole("button", { name: "Remove @remove_me" }));

    await waitFor(() => expect(screen.queryByText("@remove_me")).not.toBeInTheDocument());
    expect(screen.getByText("@keep_me", OUTSIDE_SOURCE_FILTER)).toBeInTheDocument();
    expect(deleted).toEqual(["gone"]);
  });

  it("shows a load error with a retry", async () => {
    let calls = 0;
    server.use(
      http.get(SOURCES_URL, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ detail: "boom" }, { status: 500 })
          : HttpResponse.json(mockVacancySourcesEmpty);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load your sources.");
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("You are not watching any sources yet.")).toBeInTheDocument();
  });

  it("keeps the add form disabled until the source list has loaded", async () => {
    const gate = createGate();
    server.use(
      http.get(SOURCES_URL, async () => {
        await gate.wait;
        return HttpResponse.json(mockVacancySourcesEmpty);
      }),
    );
    renderWithProviders(<InboxPage />);

    expect(getInput()).toBeDisabled();
    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();

    gate.open();
    await waitFor(() => expect(getInput()).toBeEnabled());
  });

  it("sends exactly one request when Enter is pressed twice", async () => {
    const gate = createGate();
    let posts = 0;
    server.use(
      http.post(SOURCES_URL, async () => {
        posts += 1;
        await gate.wait;
        return HttpResponse.json(
          { ...mockVacancySource, id: "once", display_name: "@only_once" },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    await user.type(getInput(), "@only_once{Enter}{Enter}");
    // Name stays "Add" while loading (aria-busy), so it is still findable
    expect(screen.getByRole("button", { name: "Add" })).toHaveAttribute("aria-busy", "true");
    gate.open();

    expect(await screen.findByText("@only_once", OUTSIDE_SOURCE_FILTER)).toBeInTheDocument();
    expect(posts).toBe(1);
  });

  it("shows the network message inline when the request cannot be sent", async () => {
    server.use(http.post(SOURCES_URL, () => HttpResponse.error()));
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    await user.type(getInput(), "@offline_channel{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Network error. Check your connection.",
    );
    expect(getInput()).toHaveValue("@offline_channel");
  });

  it("returns focus to the input after an add succeeds or fails", async () => {
    let calls = 0;
    server.use(
      http.post(SOURCES_URL, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ detail: "Already in your sources" }, { status: 409 })
          : HttpResponse.json(
              { ...mockVacancySource, id: "f", display_name: "@focus_jobs" },
              { status: 201 },
            );
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForList();

    await user.type(getInput(), "@focus_jobs");
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(getInput()).toHaveFocus();

    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByText("@focus_jobs", OUTSIDE_SOURCE_FILTER)).toBeInTheDocument();
    await waitFor(() => expect(getInput()).toHaveFocus());
  });

  it("moves focus to the next Remove button, then to the input when the list empties", async () => {
    serveSources([
      { ...mockVacancySource, id: "one", display_name: "@first_one" },
      { ...mockVacancySource, id: "two", display_name: "@second_one" },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    await user.click(await screen.findByRole("button", { name: "Remove @first_one" }));
    await waitFor(() => expect(screen.queryByText("@first_one")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Remove @second_one" })).toHaveFocus();

    await user.click(screen.getByRole("button", { name: "Remove @second_one" }));
    expect(await screen.findByText("You are not watching any sources yet.")).toBeInTheDocument();
    expect(getInput()).toHaveFocus();
  });

  it("keeps the source and shows a toast when removing fails", async () => {
    serveSources([{ ...mockVacancySource, id: "stuck", display_name: "@stuck_one" }]);
    server.use(
      http.delete(SOURCE_URL, () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    await user.click(await screen.findByRole("button", { name: "Remove @stuck_one" }));

    expect(await screen.findByText("Something went wrong. Please try again.")).toBeInTheDocument();
    expect(screen.getByText("@stuck_one", OUTSIDE_SOURCE_FILTER)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove @stuck_one" })).toBeEnabled();
  });
});
