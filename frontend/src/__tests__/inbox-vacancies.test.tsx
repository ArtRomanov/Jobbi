import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { InboxPage } from "@/pages/inbox";
import { useNewVacancyCount } from "@/entities/vacancy";
import { renderWithProviders } from "./utils";
import {
  mockVacancy,
  mockVacancyPageEmpty,
  mockVacancySource,
  mockVacancySourcesEmpty,
} from "./mocks/handlers";
import { server } from "./setup";

const VACANCIES_URL = "*/api/v1/vacancies";
const NEW_COUNT_URL = "*/api/v1/vacancies/new-count";
const SOURCES_URL = "*/api/v1/vacancy-sources";

type MockVacancy = typeof mockVacancy;

function page(items: MockVacancy[], extra: Partial<typeof mockVacancyPageEmpty> = {}) {
  return { ...mockVacancyPageEmpty, items, total: items.length, ...extra };
}

function serveVacancies(items: MockVacancy[]): void {
  server.use(http.get(VACANCIES_URL, () => HttpResponse.json(page(items))));
}

async function findCards(): Promise<HTMLElement[]> {
  const list = await screen.findByRole("list", { name: "Vacancies" });
  return within(list).getAllByRole("article");
}

/** Renders the badge count so a test can see refetches triggered by the page. */
function CountProbe() {
  const count = useNewVacancyCount();
  return <output aria-label="new count">{count}</output>;
}

describe("Inbox vacancy list", () => {
  it("requests the first page sorted by date and renders cards with fit badges and reasons", async () => {
    const requests: URLSearchParams[] = [];
    server.use(
      http.get(VACANCIES_URL, ({ request }) => {
        requests.push(new URL(request.url).searchParams);
        return HttpResponse.json(
          page([
            mockVacancy,
            {
              ...mockVacancy,
              id: "vac-2",
              title: "Frontend developer (Vue)",
              company: "Beta",
              state: "seen",
              fit: "low",
              fit_reason: "Office in Berlin, Vue instead of React",
              sources: [
                { key: "telegram:frontend_jobs", label: "@frontend_jobs" },
                { key: "telegram:vue_jobs", label: "@vue_jobs" },
              ],
            },
          ]),
        );
      }),
    );
    renderWithProviders(<InboxPage />);

    const [first, second] = await findCards();
    expect(within(first!).getByRole("heading", { name: "Senior React Developer" })).toBeInTheDocument();
    expect(within(first!).getByText("Acme")).toBeInTheDocument();
    expect(within(first!).getByText("High")).toBeInTheDocument();
    expect(within(first!).getByText("Remote React role with a matching salary")).toBeInTheDocument();
    expect(within(first!).getByText("New")).toBeInTheDocument();

    expect(within(second!).getByText("Low")).toBeInTheDocument();
    expect(within(second!).getByText("Office in Berlin, Vue instead of React")).toBeInTheDocument();
    expect(within(second!).getByText(/@frontend_jobs, @vue_jobs/)).toBeInTheDocument();
    expect(within(second!).queryByText("New")).not.toBeInTheDocument();

    expect(requests[0]?.get("sort")).toBe("date");
    expect(requests[0]?.get("page")).toBe("1");
    expect(requests[0]?.get("per_page")).toBe("20");
  });

  it("falls back to Unknown role and Unknown company", async () => {
    serveVacancies([{ ...mockVacancy, title: null, company: null }]);
    renderWithProviders(<InboxPage />);

    const [card] = await findCards();
    expect(within(card!).getByRole("heading", { name: "Unknown role" })).toBeInTheDocument();
    expect(within(card!).getByText("Unknown company")).toBeInTheDocument();
  });

  it("Show more expands only the text and sends no request", async () => {
    const longText = `${"a".repeat(300)}TAIL_TEXT`;
    let requestsAfterLoad = 0;
    serveVacancies([{ ...mockVacancy, text: longText }]);
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    const [card] = await findCards();
    await waitFor(() => expect(screen.queryByText("Loading sources…")).not.toBeInTheDocument());
    server.events.on("request:start", () => {
      requestsAfterLoad += 1;
    });

    expect(within(card!).queryByText(/TAIL_TEXT/)).not.toBeInTheDocument();
    expect(within(card!).getByText(`${"a".repeat(300)}…`)).toBeInTheDocument();

    const toggle = within(card!).getByRole("button", { name: "Show more" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);

    expect(within(card!).getByText(longText)).toBeInTheDocument();
    expect(within(card!).getByRole("button", { name: "Show less" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(within(card!).getByText("New")).toBeInTheDocument();

    await user.click(within(card!).getByRole("button", { name: "Show less" }));
    expect(within(card!).queryByText(/TAIL_TEXT/)).not.toBeInTheDocument();
    expect(requestsAfterLoad).toBe(0);
    server.events.removeAllListeners();
  });

  it("has no Show more for short texts", async () => {
    serveVacancies([mockVacancy]);
    renderWithProviders(<InboxPage />);

    const [card] = await findCards();
    expect(within(card!).queryByRole("button", { name: "Show more" })).not.toBeInTheDocument();
  });

  it("shows the empty state when there are no vacancies", async () => {
    renderWithProviders(<InboxPage />);

    expect(await screen.findByText("No vacancies yet.")).toBeInTheDocument();
    expect(
      screen.getByText("Add channels or companies and describe what you're looking for in Sources."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Vacancies" })).not.toBeInTheDocument();
  });

  it("loads the next page with Load more and hides it at the end", async () => {
    server.use(
      http.get(VACANCIES_URL, ({ request }) => {
        const pageNumber = new URL(request.url).searchParams.get("page");
        return HttpResponse.json(
          pageNumber === "2"
            ? page([{ ...mockVacancy, id: "vac-2", title: "Second page role" }], { page: 2, total: 2 })
            : page([mockVacancy], { total: 2 }),
        );
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);
    await findCards();

    await user.click(screen.getByRole("button", { name: "Load more" }));

    expect(await screen.findByRole("heading", { name: "Second page role" })).toBeInTheDocument();
    expect(await findCards()).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("shows a load error with a retry", async () => {
    let calls = 0;
    server.use(
      http.get(VACANCIES_URL, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ detail: "boom" }, { status: 500 })
          : HttpResponse.json(page([mockVacancy]));
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    expect(await screen.findByText("Could not load vacancies.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await findCards()).toHaveLength(1);
  });
});

describe("Sources panel scan status", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the relative last-checked time for sources that are not scanning", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-22T12:00:00Z"));
    server.use(
      http.get(SOURCES_URL, () =>
        HttpResponse.json({
          ...mockVacancySourcesEmpty,
          sources: [
            { ...mockVacancySource, id: "a", display_name: "@checked", last_checked_at: "2026-11-22T11:48:00Z" },
            { ...mockVacancySource, id: "b", display_name: "@never_checked" },
          ],
        }),
      ),
    );
    renderWithProviders(<InboxPage />);

    expect(await screen.findByText("Telegram · Last checked 12m ago")).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Watched sources" });
    const [, never] = within(list).getAllByRole("listitem");
    expect(within(never!).getByText("Telegram")).toBeInTheDocument();
  });

  it("polls every 5 s while scanning, refreshes the list and the badge when the scan ends, then stops", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"], shouldAdvanceTime: true });
    let sourceCalls = 0;
    let vacancyCalls = 0;
    let countCalls = 0;
    server.use(
      http.get(SOURCES_URL, () => {
        sourceCalls += 1;
        const isScanning = sourceCalls < 3;
        return HttpResponse.json({
          ...mockVacancySourcesEmpty,
          sources: [
            {
              ...mockVacancySource,
              display_name: "@scanning_one",
              scanning: isScanning,
              last_checked_at: isScanning ? null : new Date().toISOString(),
            },
          ],
        });
      }),
      http.get(VACANCIES_URL, () => {
        vacancyCalls += 1;
        return HttpResponse.json(vacancyCalls === 1 ? mockVacancyPageEmpty : page([mockVacancy]));
      }),
      http.get(NEW_COUNT_URL, () => {
        countCalls += 1;
        return HttpResponse.json({ count: countCalls === 1 ? 0 : 1 });
      }),
    );
    renderWithProviders(
      <>
        <CountProbe />
        <InboxPage />
      </>,
    );

    expect(await screen.findByText("Telegram · Scanning…")).toBeInTheDocument();
    expect(await screen.findByText("No vacancies yet.")).toBeInTheDocument();
    await waitFor(() => expect(countCalls).toBe(1));

    // First poll: still scanning, nothing refreshed
    await act(() => vi.advanceTimersByTimeAsync(5000));
    await waitFor(() => expect(sourceCalls).toBe(2));
    expect(vacancyCalls).toBe(1);

    // Second poll: scan finished → list and badge refresh
    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(await screen.findByRole("heading", { name: "Senior React Developer" })).toBeInTheDocument();
    expect(screen.getByText("Telegram · Last checked just now")).toBeInTheDocument();
    expect(vacancyCalls).toBe(2);
    await waitFor(() => expect(screen.getByRole("status", { name: "new count" })).toHaveTextContent("1"));

    // No more polling once nothing is scanning
    await act(() => vi.advanceTimersByTimeAsync(20000));
    expect(sourceCalls).toBe(3);
  });

  it("stops polling when the panel unmounts", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"], shouldAdvanceTime: true });
    let sourceCalls = 0;
    server.use(
      http.get(SOURCES_URL, () => {
        sourceCalls += 1;
        return HttpResponse.json({
          ...mockVacancySourcesEmpty,
          sources: [{ ...mockVacancySource, scanning: true }],
        });
      }),
    );
    const { unmount } = renderWithProviders(<InboxPage />);
    expect(await screen.findByText("Telegram · Scanning…")).toBeInTheDocument();

    unmount();
    await act(() => vi.advanceTimersByTimeAsync(15000));
    expect(sourceCalls).toBe(1);
  });
});
