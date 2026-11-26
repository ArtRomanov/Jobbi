import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { VacancySource } from "@/entities/vacancy-source";
import { InboxPage } from "@/pages/inbox";
import { renderWithProviders } from "./utils";
import { mockVacancySource, mockVacancySourcesEmpty } from "./mocks/handlers";
import { server } from "./setup";

const SOURCES_URL = "*/api/v1/vacancy-sources";
const SOURCE_URL = "*/api/v1/vacancy-sources/:id";

/** A promise the test resolves by hand, to hold an MSW response in flight. */
function createGate(): { wait: Promise<void>; open: () => void } {
  let open = (): void => {};
  const wait = new Promise<void>((resolve) => {
    open = resolve;
  });
  return { wait, open };
}

/** Hold the DELETE of each listed id until its gate opens; others answer at once. */
function holdDeletes(ids: readonly string[]): Map<string, () => void> {
  const gates = new Map(ids.map((id) => [id, createGate()]));
  server.use(
    http.delete(SOURCE_URL, async ({ params }) => {
      await gates.get(String(params.id))?.wait;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return new Map(ids.map((id) => [id, () => gates.get(id)?.open()]));
}

/** `count` Telegram sources named @source_1 … @source_<count>, in list order. */
function makeSources(count: number): VacancySource[] {
  return Array.from({ length: count }, (_, i) => ({
    ...mockVacancySource,
    id: `s${i + 1}`,
    key: `telegram:source_${i + 1}`,
    display_name: `@source_${i + 1}`,
  }));
}

function serveSources(sources: VacancySource[]): void {
  server.use(http.get(SOURCES_URL, () => HttpResponse.json({ ...mockVacancySourcesEmpty, sources })));
}

function getInput(): HTMLElement {
  return screen.getByLabelText("Add a channel, job board or page");
}

function getPager(): HTMLElement {
  return screen.getByRole("navigation", { name: "Sources pages" });
}

function queryPager(): HTMLElement | null {
  return screen.queryByRole("navigation", { name: "Sources pages" });
}

/** Display names of the rows on the visible page, in order. */
function visibleNames(): string[] {
  const list = screen.getByRole("list", { name: "Watched sources" });
  return within(list)
    .getAllByRole("button", { name: /^Remove / })
    .map((button) => (button.getAttribute("aria-label") ?? "").replace(/^Remove /, ""));
}

function names(from: number, to: number): string[] {
  return Array.from({ length: to - from + 1 }, (_, i) => `@source_${from + i}`);
}

async function waitForSources(): Promise<void> {
  await screen.findByRole("list", { name: "Watched sources" });
}

describe("Sources panel pagination", () => {
  it("shows no pager with 7 sources or fewer", async () => {
    serveSources(makeSources(7));
    renderWithProviders(<InboxPage />);
    await waitForSources();

    expect(visibleNames()).toEqual(names(1, 7));
    expect(queryPager()).not.toBeInTheDocument();
  });

  it("shows 7 per page with a pager from 8 sources", async () => {
    serveSources(makeSources(8));
    renderWithProviders(<InboxPage />);
    await waitForSources();

    expect(visibleNames()).toEqual(names(1, 7));
    const pager = getPager();
    expect(within(pager).getByRole("button", { name: "Previous" })).toHaveAttribute("aria-disabled", "true");
    expect(within(pager).getByRole("button", { name: "Next" })).not.toHaveAttribute("aria-disabled");
    expect(within(pager).getByRole("button", { name: "Page 1" })).toHaveAttribute("aria-current", "page");
    expect(within(pager).getByRole("button", { name: "Page 2" })).not.toHaveAttribute("aria-current");
  });

  it("Next / Previous / page numbers switch pages and keep focus on the pressed control", async () => {
    serveSources(makeSources(16));
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForSources();
    const pager = getPager();
    const next = within(pager).getByRole("button", { name: "Next" });
    const previous = within(pager).getByRole("button", { name: "Previous" });

    await user.click(next);
    expect(visibleNames()).toEqual(names(8, 14));
    expect(within(pager).getByRole("button", { name: "Page 2" })).toHaveAttribute("aria-current", "page");
    expect(next).toHaveFocus();

    await user.click(next);
    expect(visibleNames()).toEqual(names(15, 16));
    // Disabled at the end, but still focused (aria-disabled, not `disabled`)
    expect(next).toHaveAttribute("aria-disabled", "true");
    expect(next).toHaveFocus();
    await user.click(next);
    expect(visibleNames()).toEqual(names(15, 16));

    await user.click(previous);
    expect(visibleNames()).toEqual(names(8, 14));
    expect(previous).toHaveFocus();

    const pageOne = within(pager).getByRole("button", { name: "Page 1" });
    await user.click(pageOne);
    expect(visibleNames()).toEqual(names(1, 7));
    expect(pageOne).toHaveAttribute("aria-current", "page");
    expect(pageOne).toHaveFocus();
    expect(previous).toHaveAttribute("aria-disabled", "true");
  });

  it("a newly added source opens the page that shows it; focus stays on the input", async () => {
    serveSources(makeSources(8));
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForSources();
    expect(visibleNames()).toEqual(names(1, 7));

    await user.type(getInput(), "@new_one");
    await user.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(visibleNames()).toEqual(["@source_8", "@new_one"]));
    expect(within(getPager()).getByRole("button", { name: "Page 2" })).toHaveAttribute("aria-current", "page");
    await waitFor(() => expect(getInput()).toHaveFocus());
  });

  it("adding the 8th source shows the pager on page 2", async () => {
    serveSources(makeSources(7));
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForSources();

    await user.type(getInput(), "@new_one");
    await user.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(visibleNames()).toEqual(["@new_one"]));
    expect(within(getPager()).getByRole("button", { name: "Page 2" })).toHaveAttribute("aria-current", "page");
  });

  it("removing a row keeps focus logic within the page (next Remove on the same page)", async () => {
    serveSources(makeSources(10));
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForSources();
    await user.click(within(getPager()).getByRole("button", { name: "Next" }));

    await user.click(screen.getByRole("button", { name: "Remove @source_8" }));

    await waitFor(() => expect(visibleNames()).toEqual(names(9, 10)));
    expect(screen.getByRole("button", { name: "Remove @source_9" })).toHaveFocus();
  });

  it("removing the last row of the last page moves to the previous page and focuses its last Remove", async () => {
    serveSources(makeSources(15));
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForSources();
    await user.click(within(getPager()).getByRole("button", { name: "Page 3" }));
    expect(visibleNames()).toEqual(["@source_15"]);

    await user.click(screen.getByRole("button", { name: "Remove @source_15" }));

    await waitFor(() => expect(visibleNames()).toEqual(names(8, 14)));
    const pager = getPager();
    expect(within(pager).queryByRole("button", { name: "Page 3" })).not.toBeInTheDocument();
    expect(within(pager).getByRole("button", { name: "Page 2" })).toHaveAttribute("aria-current", "page");
    await waitFor(() => expect(screen.getByRole("button", { name: "Remove @source_14" })).toHaveFocus());
  });

  it("removing the 8th source (alone on page 2) hides the pager and shows page 1", async () => {
    serveSources(makeSources(8));
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForSources();
    await user.click(within(getPager()).getByRole("button", { name: "Next" }));

    await user.click(screen.getByRole("button", { name: "Remove @source_8" }));

    await waitFor(() => expect(visibleNames()).toEqual(names(1, 7)));
    expect(queryPager()).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Remove @source_7" })).toHaveFocus());
  });

  it("a rename keeps the edited row on its page and focus on its Edit", async () => {
    serveSources(makeSources(9));
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForSources();
    await user.click(within(getPager()).getByRole("button", { name: "Next" }));

    await user.click(screen.getByRole("button", { name: "Edit @source_9" }));
    const dialog = screen.getByRole("dialog", { name: "Edit source" });
    await user.type(within(dialog).getByLabelText("Name"), "Renamed");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(visibleNames()).toEqual(["@source_8", "Renamed"]);
    expect(within(getPager()).getByRole("button", { name: "Page 2" })).toHaveAttribute("aria-current", "page");
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit Renamed" })).toHaveFocus());
  });

  it("a link change (new id) keeps the new row on the same page and focuses its Edit", async () => {
    serveSources(makeSources(9));
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForSources();
    await user.click(within(getPager()).getByRole("button", { name: "Next" }));

    await user.click(screen.getByRole("button", { name: "Edit @source_8" }));
    const dialog = screen.getByRole("dialog", { name: "Edit source" });
    const link = within(dialog).getByLabelText("Link");
    await user.clear(link);
    await user.type(link, "@vue_jobs");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(visibleNames()).toEqual(["@vue_jobs", "@source_9"]);
    expect(within(getPager()).getByRole("button", { name: "Page 2" })).toHaveAttribute("aria-current", "page");
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit @vue_jobs" })).toHaveFocus());
  });

  it("the Inbox Source filter lists sources from every page", async () => {
    serveSources(makeSources(9));
    renderWithProviders(<InboxPage />);
    await waitForSources();
    expect(visibleNames()).toEqual(names(1, 7));

    const select = screen.getByRole("combobox", { name: "Source" });
    await waitFor(() =>
      expect(within(select).getByRole("option", { name: "@source_9" })).toBeInTheDocument(),
    );
    expect(within(select).getByRole("option", { name: "@source_8" })).toBeInTheDocument();
  });

  it("removing the last row of a full page focuses the next row, which slides onto this page", async () => {
    serveSources(makeSources(9));
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForSources();

    await user.click(screen.getByRole("button", { name: "Remove @source_7" }));

    await waitFor(() => expect(visibleNames()).toEqual([...names(1, 6), "@source_8"]));
    await waitFor(() => expect(screen.getByRole("button", { name: "Remove @source_8" })).toHaveFocus());
  });

  it("two removes in flight: the later one focuses the row before both, not the input", async () => {
    serveSources(makeSources(9));
    const release = holdDeletes(["s8"]);
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForSources();
    await user.click(within(getPager()).getByRole("button", { name: "Next" }));

    await user.click(screen.getByRole("button", { name: "Remove @source_8" }));
    await user.click(screen.getByRole("button", { name: "Remove @source_9" }));
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Remove @source_9" })).not.toBeInTheDocument(),
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "Remove @source_7" })).toHaveFocus());

    act(() => release.get("s8")?.());
    await waitFor(() => expect(visibleNames()).toEqual(names(1, 7)));
    expect(screen.getByRole("button", { name: "Remove @source_7" })).toHaveFocus();
  });

  it("leaves focus alone when the user moved on (pressed Next) before the DELETE returned", async () => {
    serveSources(makeSources(9));
    const release = holdDeletes(["s3"]);
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await waitForSources();

    await user.click(screen.getByRole("button", { name: "Remove @source_3" }));
    const next = within(getPager()).getByRole("button", { name: "Next" });
    await user.click(next);
    expect(next).toHaveFocus();

    act(() => release.get("s3")?.());
    await waitFor(() => expect(visibleNames()).toEqual(["@source_9"]));
    expect(next).toHaveFocus();
  });

  describe("polling", () => {
    beforeEach(() => {
      vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"], shouldAdvanceTime: true });
    });

    afterEach(() => {
      vi.useRealTimers();
      vi.restoreAllMocks();
    });

    it("updates a scanning row on page 2", async () => {
      const scanning = makeSources(8).map((source) =>
        source.id === "s8" ? { ...source, scanning: true } : source,
      );
      const done = makeSources(8).map((source) =>
        source.id === "s8" ? { ...source, last_checked_at: new Date().toISOString() } : source,
      );
      let calls = 0;
      server.use(
        http.get(SOURCES_URL, () => {
          calls += 1;
          return HttpResponse.json({ ...mockVacancySourcesEmpty, sources: calls === 1 ? scanning : done });
        }),
      );
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderWithProviders(<InboxPage />);
      await waitForSources();
      await user.click(within(getPager()).getByRole("button", { name: "Next" }));
      const row = screen.getByRole("button", { name: "Remove @source_8" }).closest("li");
      if (row === null) throw new Error("row not found");
      expect(within(row).getByText(/Scanning…/)).toBeInTheDocument();

      await act(() => vi.advanceTimersByTimeAsync(5000));

      await waitFor(() => expect(within(row).queryByText(/Scanning…/)).not.toBeInTheDocument());
      expect(within(row).getByText(/Last checked/)).toBeInTheDocument();
      expect(visibleNames()).toEqual(["@source_8"]);
    });
  });
});
