import { act, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import type { RemovedVacancySource, VacancySource } from "@/entities/vacancy-source";
import { InboxPage } from "@/pages/inbox";
import { renderWithProviders } from "./utils";
import { useEditSource } from "@/features/manage-sources/model/use-edit-source";
import { mockVacancySource, mockVacancySourcesEmpty, mockWebPreview, mockWebSource } from "./mocks/handlers";
import { server } from "./setup";

// Source names also appear as options of the Inbox source filter
const OUTSIDE_SOURCE_FILTER = { ignore: "script, style, option" };

const SOURCES_URL = "*/api/v1/vacancy-sources";
const SOURCE_URL = "*/api/v1/vacancy-sources/:id";
const PREVIEW_URL = "*/api/v1/vacancy-sources/preview";

const FIRST: VacancySource = {
  ...mockVacancySource,
  id: "one",
  key: "telegram:first_one",
  display_name: "@first_one",
};
const SECOND: VacancySource = {
  ...mockVacancySource,
  id: "two",
  key: "telegram:second_one",
  display_name: "@second_one",
};
const THIRD: VacancySource = {
  ...mockVacancySource,
  id: "three",
  key: "telegram:third_one",
  display_name: "@third_one",
};

interface ServerLog {
  /** Ids of DELETE requests, in order. */
  deleted: string[];
  /** Every request in order: "GET", "DELETE <id>", "PREVIEW", "ADD". */
  calls: string[];
}

/**
 * A tiny fake server: GET lists the live sources (and the removed ones once a
 * DELETE landed); DELETE drops the source; preview/add create a Telegram source.
 */
function serveSources(initial: VacancySource[], options: { deleteStatus?: number } = {}): ServerLog {
  let live = [...initial];
  const removed: RemovedVacancySource[] = [];
  const log: ServerLog = { deleted: [], calls: [] };
  server.use(
    http.get(SOURCES_URL, () => {
      log.calls.push("GET");
      return HttpResponse.json({ ...mockVacancySourcesEmpty, sources: live, removed_sources: removed });
    }),
    http.delete(SOURCE_URL, ({ params }) => {
      const id = String(params.id);
      log.calls.push(`DELETE ${id}`);
      log.deleted.push(id);
      if (options.deleteStatus && options.deleteStatus !== 204) {
        return HttpResponse.json({ detail: "boom" }, { status: options.deleteStatus });
      }
      const gone = live.find((source) => source.id === id);
      if (gone) removed.push({ key: gone.key, label: gone.display_name });
      live = live.filter((source) => source.id !== id);
      return new HttpResponse(null, { status: 204 });
    }),
    http.post(PREVIEW_URL, async ({ request }) => {
      log.calls.push("PREVIEW");
      const body = (await request.json()) as { input: string };
      const handle = body.input.replace(/^@/, "");
      const isWatched = live.some((source) => source.key === `telegram:${handle}`);
      return isWatched
        ? HttpResponse.json({ detail: "You already watch this source" }, { status: 409 })
        : HttpResponse.json({ kind: "telegram" });
    }),
    http.post(SOURCES_URL, async ({ request }) => {
      log.calls.push("ADD");
      const body = (await request.json()) as { input: string };
      const handle = body.input.replace(/^@/, "");
      const created: VacancySource = {
        ...mockVacancySource,
        id: `new-${handle}`,
        key: `telegram:${handle}`,
        display_name: `@${handle}`,
      };
      live = [...live, created];
      return HttpResponse.json(created, { status: 201 });
    }),
  );
  return log;
}

function useFakeTimers(): ReturnType<typeof userEvent.setup> {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"], shouldAdvanceTime: true });
  return userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
}

function getInput(): HTMLElement {
  return screen.getByLabelText("Add a channel, job board or page");
}

function sourceRowNames(): string[] {
  const list = screen.queryByRole("list", { name: "Watched sources" });
  if (!list) return [];
  return within(list)
    .getAllByRole("button", { name: /^Remove / })
    .map((button) => (button.getAttribute("aria-label") ?? "").replace(/^Remove /, ""));
}

function getSourceFilter(): HTMLElement {
  return screen.getByRole("combobox", { name: "Source" });
}

async function renderPanel(): Promise<void> {
  renderWithProviders(<InboxPage />);
  await screen.findByRole("button", { name: "Remove @first_one" });
}

function LeavableInbox() {
  const [isOnInbox, setIsOnInbox] = useState(true);
  return (
    <>
      {isOnInbox ? <InboxPage /> : <p>Another page</p>}
      <button type="button" onClick={() => setIsOnInbox(false)}>
        Leave inbox
      </button>
    </>
  );
}

describe("Remove source with Undo (backlog #10)", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("hides the row at once, shows a 'Source removed' toast with Undo and sends nothing yet", async () => {
    const user = useFakeTimers();
    const log = serveSources([FIRST, SECOND]);
    await renderPanel();

    await user.click(screen.getByRole("button", { name: "Remove @first_one" }));

    expect(sourceRowNames()).toEqual(["@second_one"]);
    expect(screen.getByText("Source removed")).toBeInTheDocument();
    const undo = screen.getByRole("button", { name: "Undo" });
    expect(undo.closest("[aria-live='polite']")).not.toBeNull();
    // Focus: next Remove (existing pickFocusAfterRemove)
    expect(screen.getByRole("button", { name: "Remove @second_one" })).toHaveFocus();

    await act(() => vi.advanceTimersByTimeAsync(4000));
    expect(log.deleted).toEqual([]);
    // The Inbox filter still lists it as a live source
    expect(within(getSourceFilter()).getByRole("option", { name: "@first_one" })).toBeInTheDocument();
  });

  it("Undo puts the row back in its place, focuses its Remove and never sends DELETE", async () => {
    const user = useFakeTimers();
    const log = serveSources([FIRST, SECOND, THIRD]);
    await renderPanel();

    await user.click(screen.getByRole("button", { name: "Remove @second_one" }));
    expect(sourceRowNames()).toEqual(["@first_one", "@third_one"]);
    expect(screen.getByRole("button", { name: "Remove @third_one" })).toHaveFocus();

    await act(() => vi.advanceTimersByTimeAsync(2000));
    await user.click(screen.getByRole("button", { name: "Undo" }));

    expect(sourceRowNames()).toEqual(["@first_one", "@second_one", "@third_one"]);
    await waitFor(() => expect(screen.getByRole("button", { name: "Remove @second_one" })).toHaveFocus());
    expect(screen.queryByText("Source removed")).not.toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(log.deleted).toEqual([]);
    expect(within(getSourceFilter()).getByRole("option", { name: "@second_one" })).toBeInTheDocument();
  });

  it("the Undo button is reachable from the keyboard", async () => {
    const user = useFakeTimers();
    const log = serveSources([FIRST]);
    await renderPanel();

    await user.click(screen.getByRole("button", { name: "Remove @first_one" }));
    const undo = screen.getByRole("button", { name: "Undo" });
    act(() => undo.focus());
    await user.keyboard("{Enter}");

    expect(sourceRowNames()).toEqual(["@first_one"]);
    await waitFor(() => expect(screen.getByRole("button", { name: "Remove @first_one" })).toHaveFocus());
    expect(log.deleted).toEqual([]);
  });

  it("when the toast expires, sends DELETE once, then the Inbox filter shows it as (removed)", async () => {
    const user = useFakeTimers();
    const log = serveSources([FIRST, SECOND]);
    await renderPanel();
    await waitFor(() => expect(log.calls).toEqual(["GET"]));

    await user.click(screen.getByRole("button", { name: "Remove @first_one" }));
    await act(() => vi.advanceTimersByTimeAsync(5000));

    await waitFor(() => expect(log.deleted).toEqual(["one"]));
    expect(screen.queryByText("Source removed")).not.toBeInTheDocument();
    // Side effects after the DELETE: removed list re-fetched, filter updated
    await waitFor(() => expect(log.calls).toEqual(["GET", "DELETE one", "GET"]));
    expect(
      await within(getSourceFilter()).findByRole("option", { name: "@first_one (removed)" }),
    ).toBeInTheDocument();
    expect(sourceRowNames()).toEqual(["@second_one"]);

    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(log.deleted).toEqual(["one"]);
  });

  it("brings the row back with an error toast when the delayed DELETE fails", async () => {
    const user = useFakeTimers();
    const log = serveSources([FIRST], { deleteStatus: 500 });
    await renderPanel();

    await user.click(screen.getByRole("button", { name: "Remove @first_one" }));
    expect(sourceRowNames()).toEqual([]);
    await act(() => vi.advanceTimersByTimeAsync(5000));

    expect(await screen.findByText("Something went wrong. Please try again.")).toBeInTheDocument();
    expect(sourceRowNames()).toEqual(["@first_one"]);
    expect(screen.getByRole("button", { name: "Remove @first_one" })).toBeEnabled();
    expect(log.deleted).toEqual(["one"]);
  });

  it("treats a 404 on the delayed DELETE as already removed", async () => {
    const user = useFakeTimers();
    serveSources([FIRST, SECOND], { deleteStatus: 404 });
    await renderPanel();

    await user.click(screen.getByRole("button", { name: "Remove @first_one" }));
    await act(() => vi.advanceTimersByTimeAsync(5000));

    await waitFor(() => expect(screen.queryByText("Source removed")).not.toBeInTheDocument());
    await act(() => vi.advanceTimersByTimeAsync(100));
    expect(sourceRowNames()).toEqual(["@second_one"]);
    expect(screen.queryByText(/went wrong|not found/i)).not.toBeInTheDocument();
  });

  it("gives every remove its own toast and pending delete", async () => {
    const user = useFakeTimers();
    const log = serveSources([FIRST, SECOND, THIRD]);
    await renderPanel();

    await user.click(screen.getByRole("button", { name: "Remove @first_one" }));
    await act(() => vi.advanceTimersByTimeAsync(1000));
    await user.click(screen.getByRole("button", { name: "Remove @second_one" }));

    expect(sourceRowNames()).toEqual(["@third_one"]);
    const undos = screen.getAllByRole("button", { name: "Undo" });
    expect(undos).toHaveLength(2);

    // Undo the second one only
    await user.click(undos[1]!);
    expect(sourceRowNames()).toEqual(["@second_one", "@third_one"]);

    await act(() => vi.advanceTimersByTimeAsync(5000));
    await waitFor(() => expect(log.deleted).toEqual(["one"]));
    expect(sourceRowNames()).toEqual(["@second_one", "@third_one"]);
  });

  it("sends a pending DELETE when the panel unmounts (leaving the Inbox)", async () => {
    const user = useFakeTimers();
    const log = serveSources([FIRST, SECOND]);
    renderWithProviders(<LeavableInbox />);
    await screen.findByRole("button", { name: "Remove @first_one" });

    await user.click(screen.getByRole("button", { name: "Remove @first_one" }));
    await user.click(screen.getByRole("button", { name: "Leave inbox" }));

    expect(screen.getByText("Another page")).toBeInTheDocument();
    expect(screen.queryByText("Source removed")).not.toBeInTheDocument();
    await waitFor(() => expect(log.deleted).toEqual(["one"]));
    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(log.deleted).toEqual(["one"]);
  });

  it("sends a pending DELETE with keepalive when the page is hidden for good (pagehide)", async () => {
    const user = useFakeTimers();
    const log = serveSources([FIRST, SECOND]);
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    await renderPanel();

    await user.click(screen.getByRole("button", { name: "Remove @first_one" }));
    act(() => {
      window.dispatchEvent(new Event("pagehide"));
    });

    await waitFor(() => expect(log.deleted).toEqual(["one"]));
    const deleteCalls = fetchSpy.mock.calls.filter(([, init]) => init?.method === "DELETE");
    fetchSpy.mockRestore();
    expect(deleteCalls.map(([, init]) => init?.keepalive)).toEqual([true]);
    expect(screen.queryByText("Source removed")).not.toBeInTheDocument();
    await waitFor(() => expect(log.calls[log.calls.length - 1]).toBe("GET"));
    expect(sourceRowNames()).toEqual(["@second_one"]);

    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(log.deleted).toEqual(["one"]);
  });

  it("a poll while the delete is pending does not bring the row back", async () => {
    const user = useFakeTimers();
    // A scanning source makes the panel poll every 5 s
    const log = serveSources([FIRST, { ...SECOND, scanning: true }]);
    await renderPanel();

    await user.click(screen.getByRole("button", { name: "Remove @first_one" }));
    // Hovering keeps the toast (and so the Undo window) open past the poll
    await user.hover(screen.getByText("Source removed"));
    await act(() => vi.advanceTimersByTimeAsync(6000));

    await waitFor(() => expect(log.calls.filter((call) => call === "GET").length).toBeGreaterThanOrEqual(2));
    expect(sourceRowNames()).toEqual(["@second_one"]);
    expect(log.deleted).toEqual([]);

    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(sourceRowNames()).toEqual(["@first_one", "@second_one"]);
    expect(log.deleted).toEqual([]);
  });

  it("adding the same source while its delete is pending sends the DELETE first, then adds it", async () => {
    const user = useFakeTimers();
    const log = serveSources([FIRST, SECOND]);
    await renderPanel();

    await user.click(screen.getByRole("button", { name: "Remove @first_one" }));
    await user.type(getInput(), "@first_one");
    await user.click(screen.getByRole("button", { name: "Add" }));

    expect(await screen.findByRole("button", { name: "Remove @first_one" })).toBeInTheDocument();
    // The pending DELETE lands before the preview's duplicate check
    expect(log.calls.indexOf("DELETE one")).toBeGreaterThan(0);
    expect(log.calls.indexOf("DELETE one")).toBeLessThan(log.calls.indexOf("PREVIEW"));
    expect(log.calls.indexOf("PREVIEW")).toBeLessThan(log.calls.indexOf("ADD"));
    expect(screen.queryByText("Source removed")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(sourceRowNames()).toEqual(["@second_one", "@first_one"]);

    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(log.deleted).toEqual(["one"]);
  });

  it("focuses the previous Remove, then the input, as rows are removed from the end", async () => {
    const user = useFakeTimers();
    serveSources([FIRST, SECOND]);
    await renderPanel();

    await user.click(screen.getByRole("button", { name: "Remove @second_one" }));
    expect(screen.getByRole("button", { name: "Remove @first_one" })).toHaveFocus();

    await user.click(screen.getByRole("button", { name: "Remove @first_one" }));
    expect(screen.getByText("You are not watching any sources yet.")).toBeInTheDocument();
    expect(getInput()).toHaveFocus();
    expect(screen.getByText("@first_one", { selector: "option" })).toBeInTheDocument();
    expect(screen.queryByText("@first_one", OUTSIDE_SOURCE_FILTER)).not.toBeInTheDocument();
  });

  it("an Edit link change to a source whose delete is pending sends the DELETE first", async () => {
    const user = useFakeTimers();
    const log = serveSources([FIRST, SECOND]);
    server.use(
      http.patch(SOURCE_URL, async ({ params, request }) => {
        log.calls.push(`PATCH ${String(params.id)}`);
        const body = (await request.json()) as { input: string };
        const handle = body.input.replace(/^@/, "");
        return HttpResponse.json({
          ...SECOND,
          id: `new-${handle}`,
          key: `telegram:${handle}`,
          display_name: `@${handle}`,
        });
      }),
    );
    await renderPanel();

    await user.click(screen.getByRole("button", { name: "Remove @first_one" }));
    await user.click(screen.getByRole("button", { name: "Edit @second_one" }));
    const dialog = screen.getByRole("dialog", { name: "Edit source" });
    const link = within(dialog).getByLabelText("Link");
    await user.clear(link);
    await user.type(link, "@first_one");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(log.calls.indexOf("DELETE one")).toBeGreaterThan(0);
    expect(log.calls.indexOf("DELETE one")).toBeLessThan(log.calls.indexOf("PREVIEW"));
    expect(log.calls.indexOf("PREVIEW")).toBeLessThan(log.calls.indexOf("PATCH two"));
    expect(screen.queryByText("Source removed")).not.toBeInTheDocument();
    expect(sourceRowNames()).toEqual(["@first_one"]);
  });

  it("logging out within the Undo window still sends ONE DELETE with the token from Remove time", async () => {
    localStorage.setItem("jobbi_token", "token-at-remove");
    const user = useFakeTimers();
    const log = serveSources([FIRST, SECOND]);
    const authHeaders: (string | null)[] = [];
    server.use(
      http.delete(SOURCE_URL, ({ params, request }) => {
        log.deleted.push(String(params.id));
        authHeaders.push(request.headers.get("Authorization"));
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderWithProviders(<LeavableInbox />);
    await screen.findByRole("button", { name: "Remove @first_one" });

    await user.click(screen.getByRole("button", { name: "Remove @first_one" }));
    // Logout: the token goes first, then the protected page unmounts
    localStorage.removeItem("jobbi_token");
    await user.click(screen.getByRole("button", { name: "Leave inbox" }));

    await waitFor(() => expect(log.deleted).toEqual(["one"]));
    expect(authHeaders).toEqual(["Bearer token-at-remove"]);
    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(log.deleted).toEqual(["one"]);
  });

  it("Re-check in the add flow's web preview sends a pending DELETE first", async () => {
    const user = useFakeTimers();
    const log = serveSources([FIRST, SECOND]);
    server.use(
      http.post(PREVIEW_URL, () => {
        log.calls.push("PREVIEW");
        return HttpResponse.json(mockWebPreview);
      }),
    );
    await renderPanel();

    await user.type(getInput(), "https://jobs.example.com/list");
    await user.click(screen.getByRole("button", { name: "Add" }));
    const preview = await screen.findByRole("region", { name: /Found/ });
    await user.click(screen.getByRole("button", { name: "Remove @first_one" }));
    expect(log.deleted).toEqual([]);

    await user.click(within(preview).getByRole("button", { name: "Re-check" }));

    await waitFor(() => expect(log.calls.filter((call) => call === "PREVIEW")).toHaveLength(2));
    expect(log.calls.indexOf("DELETE one")).toBeGreaterThan(-1);
    expect(log.calls.indexOf("DELETE one")).toBeLessThan(log.calls.lastIndexOf("PREVIEW"));
    expect(screen.queryByText("Source removed")).not.toBeInTheDocument();
  });

  it("Re-check in the Edit dialog's preview runs beforeLinkChange first", async () => {
    const calls: string[] = [];
    server.use(
      http.post(PREVIEW_URL, () => {
        calls.push("PREVIEW");
        return HttpResponse.json(mockWebPreview);
      }),
    );
    const beforeLinkChange = vi.fn(async (): Promise<void> => {
      calls.push("FLUSH");
    });
    const { result } = renderHook(() =>
      useEditSource(mockWebSource as unknown as VacancySource, vi.fn(), beforeLinkChange),
    );

    await act(async () => {
      await result.current.submit({ name: null, link: "https://other.example.com/jobs", jobLinkContains: null });
    });
    expect(result.current.preview).not.toBeNull();
    await act(async () => {
      await result.current.recheck("/vacancy/");
    });

    expect(calls).toEqual(["FLUSH", "PREVIEW", "FLUSH", "PREVIEW"]);
  });
});
