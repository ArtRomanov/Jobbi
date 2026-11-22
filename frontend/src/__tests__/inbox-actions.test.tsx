import { useState } from "react";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { InboxPage } from "@/pages/inbox";
import { VacancyList } from "@/pages/inbox/ui/vacancy-list";
import { DEFAULT_INBOX_FILTERS } from "@/features/inbox-filters";
import { useNewVacancyCount } from "@/entities/vacancy";
import { renderWithProviders } from "./utils";
import { mockVacancy, mockVacancyPageEmpty } from "./mocks/handlers";
import { server } from "./setup";

const VACANCIES_URL = "*/api/v1/vacancies";
const NEW_COUNT_URL = "*/api/v1/vacancies/new-count";
const ACTION_URL = "*/api/v1/vacancies/:id/:action";

type MockVacancy = typeof mockVacancy;

const SECOND: MockVacancy = {
  ...mockVacancy,
  id: "vac-2",
  title: "Frontend Engineer",
  company: "Beta",
  url: "https://t.me/frontend_jobs/102",
};

function serveVacancies(items: MockVacancy[]): void {
  server.use(
    http.get(VACANCIES_URL, () =>
      HttpResponse.json({ ...mockVacancyPageEmpty, items, total: items.length }),
    ),
  );
}

interface RecordedAction {
  id: string;
  action: string;
}

/** Records every state-change POST; `fail` maps an action to an error status. */
function recordActions(fail: Partial<Record<string, number>> = {}): RecordedAction[] {
  const recorded: RecordedAction[] = [];
  server.use(
    http.post(ACTION_URL, ({ params }) => {
      const action = String(params.action);
      recorded.push({ id: String(params.id), action });
      const status = fail[action];
      return status
        ? HttpResponse.json({ detail: "boom" }, { status })
        : new HttpResponse(null, { status: 204 });
    }),
  );
  return recorded;
}

function countNewCountCalls(): () => number {
  let calls = 0;
  server.use(
    http.get(NEW_COUNT_URL, () => {
      calls += 1;
      return HttpResponse.json({ count: 0 });
    }),
  );
  return () => calls;
}

function CountProbe() {
  const count = useNewVacancyCount();
  return <output aria-label="new count">{count}</output>;
}

/** Inbox that can be left while the app (ToastProvider) stays mounted. */
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

/** The list alone, with a button that bumps `refreshKey` (a background reload). */
function RefreshableList() {
  const [refreshKey, setRefreshKey] = useState(0);
  return (
    <>
      <VacancyList refreshKey={refreshKey} filters={DEFAULT_INBOX_FILTERS} onListEmptied={() => undefined} />
      <button type="button" onClick={() => setRefreshKey((key) => key + 1)}>
        Refresh
      </button>
    </>
  );
}

async function findCard(name: string): Promise<HTMLElement> {
  const heading = await screen.findByRole("heading", { name });
  return heading.closest("article")!;
}

function cardHeadings(): string[] {
  const list = screen.getByRole("list", { name: "Vacancies" });
  return within(list)
    .getAllByRole("heading")
    .map((heading) => heading.textContent ?? "");
}

describe("Inbox card actions", () => {
  let openSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
  });

  afterEach(() => {
    openSpy.mockRestore();
    vi.useRealTimers();
  });

  describe("Open source", () => {
    it("opens the url in a new tab without opener, marks the card seen and refetches the badge", async () => {
      serveVacancies([mockVacancy]);
      const recorded = recordActions();
      const newCountCalls = countNewCountCalls();
      const user = userEvent.setup();
      renderWithProviders(
        <>
          <CountProbe />
          <InboxPage />
        </>,
      );
      const card = await findCard("Senior React Developer");
      await waitFor(() => expect(newCountCalls()).toBe(1));

      await user.click(within(card).getByRole("button", { name: /^Open source for / }));

      expect(openSpy).toHaveBeenCalledWith(
        "https://t.me/frontend_jobs/101",
        "_blank",
        expect.stringContaining("noopener"),
      );
      expect(String(openSpy.mock.calls[0]?.[2])).toContain("noreferrer");
      await waitFor(() => expect(recorded).toEqual([{ id: "vac-1", action: "seen" }]));
      expect(within(card).queryByText("New")).not.toBeInTheDocument();
      await waitFor(() => expect(newCountCalls()).toBe(2));
    });

    it("does not send seen again for a card that is already seen", async () => {
      serveVacancies([{ ...mockVacancy, state: "seen" }]);
      const recorded = recordActions();
      const user = userEvent.setup();
      renderWithProviders(<InboxPage />);
      const card = await findCard("Senior React Developer");

      await user.click(within(card).getByRole("button", { name: /^Open source for / }));

      expect(openSpy).toHaveBeenCalledTimes(1);
      expect(recorded).toEqual([]);
    });

    it("never opens a javascript: url", async () => {
      serveVacancies([{ ...mockVacancy, url: "javascript:alert(1)" }]);
      const recorded = recordActions();
      const user = userEvent.setup();
      renderWithProviders(<InboxPage />);
      const card = await findCard("Senior React Developer");

      const button = within(card).getByRole("button", { name: /^Open source for / });
      expect(button).toBeDisabled();
      await user.click(button);

      expect(openSpy).not.toHaveBeenCalled();
      expect(recorded).toEqual([]);
    });

    it("shows the card as new again when the seen request fails", async () => {
      serveVacancies([mockVacancy]);
      recordActions({ seen: 500 });
      const user = userEvent.setup();
      renderWithProviders(<InboxPage />);
      const card = await findCard("Senior React Developer");

      await user.click(within(card).getByRole("button", { name: /^Open source for / }));

      expect(openSpy).toHaveBeenCalledTimes(1);
      await waitFor(() => expect(within(card).getByText("New")).toBeInTheDocument());
    });
  });

  describe("Dismiss", () => {
    it("removes the card at once and Undo brings it back as seen in its place", async () => {
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"], shouldAdvanceTime: true });
      serveVacancies([mockVacancy, SECOND]);
      const recorded = recordActions();
      const newCountCalls = countNewCountCalls();
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderWithProviders(
        <>
          <CountProbe />
          <InboxPage />
        </>,
      );
      const card = await findCard("Senior React Developer");
      await waitFor(() => expect(newCountCalls()).toBe(1));

      await user.click(within(card).getByRole("button", { name: /^Dismiss / }));

      expect(screen.queryByRole("heading", { name: "Senior React Developer" })).not.toBeInTheDocument();
      expect(screen.getByText("Dismissed")).toBeInTheDocument();
      await waitFor(() => expect(recorded).toEqual([{ id: "vac-1", action: "dismiss" }]));
      await waitFor(() => expect(newCountCalls()).toBe(2));

      await act(() => vi.advanceTimersByTimeAsync(2000));
      await user.click(screen.getByRole("button", { name: "Undo" }));

      const restored = await findCard("Senior React Developer");
      expect(within(restored).queryByText("New")).not.toBeInTheDocument();
      expect(cardHeadings()).toEqual(["Senior React Developer", "Frontend Engineer"]);
      expect(recorded).toEqual([
        { id: "vac-1", action: "dismiss" },
        { id: "vac-1", action: "restore" },
      ]);
      expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
      await waitFor(() => expect(newCountCalls()).toBe(3));
    });

    it("stays gone when Undo is not used within 5 seconds", async () => {
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"], shouldAdvanceTime: true });
      serveVacancies([mockVacancy, SECOND]);
      const recorded = recordActions();
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderWithProviders(<InboxPage />);
      const card = await findCard("Senior React Developer");

      await user.click(within(card).getByRole("button", { name: /^Dismiss / }));
      expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();

      await act(() => vi.advanceTimersByTimeAsync(5000));

      expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
      expect(screen.queryByText("Dismissed")).not.toBeInTheDocument();
      expect(cardHeadings()).toEqual(["Frontend Engineer"]);
      expect(recorded).toEqual([{ id: "vac-1", action: "dismiss" }]);
    });

    it("ends the Undo window when the user leaves the Inbox", async () => {
      serveVacancies([mockVacancy]);
      const recorded = recordActions();
      const user = userEvent.setup();
      renderWithProviders(<LeavableInbox />);
      const card = await findCard("Senior React Developer");

      await user.click(within(card).getByRole("button", { name: /^Dismiss / }));
      expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Leave inbox" }));

      expect(screen.getByText("Another page")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
      await waitFor(() => expect(recorded).toEqual([{ id: "vac-1", action: "dismiss" }]));
    });

    it("puts the card back and shows an error toast when the dismiss fails", async () => {
      serveVacancies([mockVacancy, SECOND]);
      const recorded = recordActions({ dismiss: 500 });
      const newCountCalls = countNewCountCalls();
      const user = userEvent.setup();
      renderWithProviders(
        <>
          <CountProbe />
          <InboxPage />
        </>,
      );
      const card = await findCard("Senior React Developer");
      await waitFor(() => expect(newCountCalls()).toBe(1));

      await user.click(within(card).getByRole("button", { name: /^Dismiss / }));

      expect(await screen.findByText("Something went wrong. Please try again.")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
      const restored = await findCard("Senior React Developer");
      // Restored as it was: still new
      expect(within(restored).getByText("New")).toBeInTheDocument();
      expect(cardHeadings()).toEqual(["Senior React Developer", "Frontend Engineer"]);
      expect(recorded).toEqual([{ id: "vac-1", action: "dismiss" }]);
      await waitFor(() => expect(newCountCalls()).toBe(2));
    });

    it("keeps the card dismissed and shows an error when the restore fails", async () => {
      serveVacancies([mockVacancy]);
      recordActions({ restore: 500 });
      const user = userEvent.setup();
      renderWithProviders(<InboxPage />);
      const card = await findCard("Senior React Developer");

      await user.click(within(card).getByRole("button", { name: /^Dismiss / }));
      await user.click(screen.getByRole("button", { name: "Undo" }));

      expect(await screen.findByText("Something went wrong. Please try again.")).toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: "Senior React Developer" })).not.toBeInTheDocument();
    });

    it("restores only after a still-pending dismiss lands, and only once", async () => {
      serveVacancies([mockVacancy, SECOND]);
      const recorded: RecordedAction[] = [];
      let releaseDismiss: () => void = () => undefined;
      const dismissGate = new Promise<void>((resolve) => {
        releaseDismiss = resolve;
      });
      server.use(
        http.post(ACTION_URL, async ({ params }) => {
          const action = String(params.action);
          recorded.push({ id: String(params.id), action });
          if (action === "dismiss") await dismissGate;
          return new HttpResponse(null, { status: 204 });
        }),
      );
      const user = userEvent.setup();
      renderWithProviders(<InboxPage />);
      const card = await findCard("Senior React Developer");

      await user.click(within(card).getByRole("button", { name: /^Dismiss / }));
      await user.click(screen.getByRole("button", { name: "Undo" }));
      await waitFor(() => expect(recorded).toEqual([{ id: "vac-1", action: "dismiss" }]));

      releaseDismiss();

      await findCard("Senior React Developer");
      expect(recorded).toEqual([
        { id: "vac-1", action: "dismiss" },
        { id: "vac-1", action: "restore" },
      ]);
      expect(cardHeadings()).toEqual(["Senior React Developer", "Frontend Engineer"]);
    });

    it("does not insert an undone card into a list loaded after the dismiss", async () => {
      server.use(
        http.get(VACANCIES_URL, ({ request }) => {
          const isNewOnly = new URL(request.url).searchParams.get("state") === "new";
          const items = isNewOnly ? [SECOND] : [mockVacancy, SECOND];
          return HttpResponse.json({ ...mockVacancyPageEmpty, items, total: items.length });
        }),
      );
      const recorded = recordActions();
      const user = userEvent.setup();
      renderWithProviders(<InboxPage />);
      const card = await findCard("Senior React Developer");

      await user.click(within(card).getByRole("button", { name: /^Dismiss / }));
      await user.click(screen.getByRole("radio", { name: "New" }));
      await waitFor(() => expect(cardHeadings()).toEqual(["Frontend Engineer"]));
      await user.click(screen.getByRole("button", { name: "Undo" }));

      await waitFor(() =>
        expect(recorded).toEqual([
          { id: "vac-1", action: "dismiss" },
          { id: "vac-1", action: "restore" },
        ]),
      );
      expect(cardHeadings()).toEqual(["Frontend Engineer"]);
    });

    it("does not put an undone card back into a state filter it no longer matches", async () => {
      const newCards = [mockVacancy, { ...SECOND, state: "new" as const }];
      server.use(
        http.get(VACANCIES_URL, ({ request }) => {
          const isNewOnly = new URL(request.url).searchParams.get("state") === "new";
          const items = isNewOnly ? newCards : [mockVacancy, SECOND];
          return HttpResponse.json({ ...mockVacancyPageEmpty, items, total: items.length });
        }),
      );
      const recorded = recordActions();
      const user = userEvent.setup();
      renderWithProviders(<InboxPage />);
      await findCard("Senior React Developer");
      await user.click(screen.getByRole("radio", { name: "New" }));
      await waitFor(() => expect(screen.getByRole("radio", { name: "New" })).toHaveAttribute("aria-checked", "true"));
      const card = await findCard("Senior React Developer");

      await user.click(within(card).getByRole("button", { name: /^Dismiss / }));
      await user.click(screen.getByRole("button", { name: "Undo" }));

      await waitFor(() =>
        expect(recorded).toEqual([
          { id: "vac-1", action: "dismiss" },
          { id: "vac-1", action: "restore" },
        ]),
      );
      // Undo restores it as seen, which the New filter excludes
      await waitFor(() => expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument());
      expect(cardHeadings()).toEqual(["Frontend Engineer"]);
      // Total not bumped: one card listed out of one, so no "Load more"
      expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
    });

    it("keeps a card dismissed during a background reload hidden, and Undo still restores it", async () => {
      const THIRD: MockVacancy = { ...mockVacancy, id: "vac-3", title: "Platform Engineer" };
      let listCalls = 0;
      let releaseReload: () => void = () => undefined;
      const reloadGate = new Promise<void>((resolve) => {
        releaseReload = resolve;
      });
      server.use(
        http.get(VACANCIES_URL, async () => {
          listCalls += 1;
          // The reload's snapshot is taken before the dismiss commits
          const items = listCalls === 1 ? [mockVacancy, SECOND] : [mockVacancy, SECOND, THIRD];
          if (listCalls > 1) await reloadGate;
          return HttpResponse.json({ ...mockVacancyPageEmpty, items, total: items.length });
        }),
      );
      const recorded = recordActions();
      const user = userEvent.setup();
      renderWithProviders(<RefreshableList />);
      const card = await findCard("Senior React Developer");

      await user.click(screen.getByRole("button", { name: "Refresh" }));
      await waitFor(() => expect(listCalls).toBe(2));
      await user.click(within(card).getByRole("button", { name: /^Dismiss / }));
      await waitFor(() => expect(recorded).toEqual([{ id: "vac-1", action: "dismiss" }]));

      releaseReload();

      await findCard("Platform Engineer");
      expect(cardHeadings()).toEqual(["Frontend Engineer", "Platform Engineer"]);
      expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Undo" }));

      const restored = await findCard("Senior React Developer");
      expect(within(restored).queryByText("New")).not.toBeInTheDocument();
      expect(cardHeadings()).toEqual(["Senior React Developer", "Frontend Engineer", "Platform Engineer"]);
      expect(recorded).toEqual([
        { id: "vac-1", action: "dismiss" },
        { id: "vac-1", action: "restore" },
      ]);
      expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
    });

    it("moves focus to the next card's Dismiss, then to the page heading when the list empties", async () => {
      serveVacancies([mockVacancy, SECOND]);
      recordActions();
      const user = userEvent.setup();
      renderWithProviders(<InboxPage />);
      const first = await findCard("Senior React Developer");
      const second = await findCard("Frontend Engineer");

      await user.click(within(first).getByRole("button", { name: /^Dismiss / }));
      expect(within(second).getByRole("button", { name: /^Dismiss / })).toHaveFocus();

      await user.click(within(second).getByRole("button", { name: /^Dismiss / }));
      expect(screen.getByRole("heading", { level: 1, name: "Inbox" })).toHaveFocus();
    });

    it("focuses the previous card's Dismiss when the last card is dismissed", async () => {
      serveVacancies([mockVacancy, SECOND]);
      recordActions();
      const user = userEvent.setup();
      renderWithProviders(<InboxPage />);
      const first = await findCard("Senior React Developer");
      const second = await findCard("Frontend Engineer");

      await user.click(within(second).getByRole("button", { name: /^Dismiss / }));
      expect(within(first).getByRole("button", { name: /^Dismiss / })).toHaveFocus();
    });
  });

  describe("Load more after a dismiss", () => {
    it("re-reads the previous page so the card that shifted onto it is not skipped", async () => {
      const all = ["A", "B", "C", "D"].map((title, i) => ({
        ...mockVacancy,
        id: `vac-${i + 1}`,
        title,
      }));
      const dismissed = new Set<string>();
      const requestedPages: string[] = [];
      // Server pages of 2, so a dismiss on page 1 shifts C from page 2 onto page 1
      server.use(
        http.get(VACANCIES_URL, ({ request }) => {
          const pageNumber = Number(new URL(request.url).searchParams.get("page"));
          requestedPages.push(String(pageNumber));
          const visible = all.filter((v) => !dismissed.has(v.id));
          return HttpResponse.json({
            ...mockVacancyPageEmpty,
            items: visible.slice((pageNumber - 1) * 2, pageNumber * 2),
            total: visible.length,
          });
        }),
        http.post(ACTION_URL, ({ params }) => {
          if (params.action === "dismiss") dismissed.add(String(params.id));
          return new HttpResponse(null, { status: 204 });
        }),
      );
      const user = userEvent.setup();
      renderWithProviders(<InboxPage />);
      const card = await findCard("A");

      await user.click(within(card).getByRole("button", { name: /^Dismiss / }));
      await waitFor(() => expect(dismissed.has("vac-1")).toBe(true));
      await user.click(screen.getByRole("button", { name: "Load more" }));

      await findCard("D");
      expect(cardHeadings()).toEqual(["B", "C", "D"]);
      expect(requestedPages.slice(1).sort()).toEqual(["1", "2"]);
      expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
    });

    it("does not re-add a card whose dismiss is still in flight", async () => {
      const all = ["A", "B", "C", "D"].map((title, i) => ({
        ...mockVacancy,
        id: `vac-${i + 1}`,
        title,
      }));
      let releaseDismiss: () => void = () => undefined;
      const dismissGate = new Promise<void>((resolve) => {
        releaseDismiss = resolve;
      });
      // Server pages of 2; the dismiss has not committed, so page 1 still has A
      server.use(
        http.get(VACANCIES_URL, ({ request }) => {
          const pageNumber = Number(new URL(request.url).searchParams.get("page"));
          return HttpResponse.json({
            ...mockVacancyPageEmpty,
            items: all.slice((pageNumber - 1) * 2, pageNumber * 2),
            total: all.length,
          });
        }),
        http.post(ACTION_URL, async () => {
          await dismissGate;
          return new HttpResponse(null, { status: 204 });
        }),
      );
      const user = userEvent.setup();
      renderWithProviders(<InboxPage />);
      const card = await findCard("A");

      await user.click(within(card).getByRole("button", { name: /^Dismiss / }));
      await user.click(screen.getByRole("button", { name: "Load more" }));

      await findCard("D");
      expect(cardHeadings()).toEqual(["B", "C", "D"]);
      // The server total still counts A; the hidden card must not keep "Load more" up
      expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
      releaseDismiss();
    });
  });
});
