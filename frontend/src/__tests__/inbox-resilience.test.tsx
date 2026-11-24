import { act, screen, waitFor, within } from "@testing-library/react";
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

const SOURCES_URL = "*/api/v1/vacancy-sources";
const VACANCIES_URL = "*/api/v1/vacancies";
const AI_NOTICE =
  "Vacancy search is temporarily unavailable — new posts will be checked when it's back";

type Status = typeof mockVacancySourcesEmpty.status;

function serveStatus(status: Status): void {
  server.use(http.get(SOURCES_URL, () => HttpResponse.json({ ...mockVacancySourcesEmpty, status })));
}

function getNotices(): HTMLElement {
  return screen.getByRole("status", { name: "Vacancy search status" });
}

async function waitForList(): Promise<void> {
  await waitFor(() => expect(screen.queryByText("Loading sources…")).not.toBeInTheDocument());
}

function noticeTexts(): string[] {
  return Array.from(getNotices().querySelectorAll("p"), (p) => p.textContent ?? "");
}

let visibility: DocumentVisibilityState = "visible";

function setVisibility(state: DocumentVisibilityState): void {
  visibility = state;
  document.dispatchEvent(new Event("visibilitychange"));
}

describe("Sources panel status notices", () => {
  it.each<[string, Status, string[]]>([
    ["nothing", { ai_unavailable: false, limit_reached: false, waiting_count: 0, filtered_last_24h: 0 }, []],
    [
      "the plural limit notice",
      { ai_unavailable: false, limit_reached: true, waiting_count: 42, filtered_last_24h: 0 },
      ["Daily limit reached — 42 posts are waiting"],
    ],
    [
      "the singular limit notice",
      { ai_unavailable: false, limit_reached: true, waiting_count: 1, filtered_last_24h: 0 },
      ["Daily limit reached — 1 post is waiting"],
    ],
    [
      "the AI notice",
      { ai_unavailable: true, limit_reached: false, waiting_count: 7, filtered_last_24h: 0 },
      [AI_NOTICE],
    ],
    [
      "both notices",
      { ai_unavailable: true, limit_reached: true, waiting_count: 3, filtered_last_24h: 0 },
      ["Daily limit reached — 3 posts are waiting", AI_NOTICE],
    ],
  ])("shows %s", async (_name, status, expected) => {
    serveStatus(status);
    renderWithProviders(<InboxPage />);
    await waitForList();

    expect(noticeTexts()).toEqual(expected);
  });
});

describe("Sources panel refresh", () => {
  beforeEach(() => {
    visibility = "visible";
    vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibility);
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"], shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("re-fetches every 60 s while visible and updates the notices", async () => {
    let calls = 0;
    server.use(
      http.get(SOURCES_URL, () => {
        calls += 1;
        const status: Status =
          calls === 1
            ? { ai_unavailable: false, limit_reached: false, waiting_count: 0, filtered_last_24h: 0 }
            : { ai_unavailable: true, limit_reached: true, waiting_count: 1, filtered_last_24h: 0 };
        return HttpResponse.json({ ...mockVacancySourcesEmpty, status });
      }),
    );
    renderWithProviders(<InboxPage />);
    await waitForList();
    expect(noticeTexts()).toEqual([]);

    await act(() => vi.advanceTimersByTimeAsync(59_000));
    expect(calls).toBe(1);

    await act(() => vi.advanceTimersByTimeAsync(1_000));
    await waitFor(() =>
      expect(noticeTexts()).toEqual(["Daily limit reached — 1 post is waiting", AI_NOTICE]),
    );
    expect(calls).toBe(2);

    await act(() => vi.advanceTimersByTimeAsync(60_000));
    expect(calls).toBe(3);
  });

  it("pauses the 60 s refresh while the page is hidden and resumes on return", async () => {
    let calls = 0;
    server.use(
      http.get(SOURCES_URL, () => {
        calls += 1;
        return HttpResponse.json(mockVacancySourcesEmpty);
      }),
    );
    renderWithProviders(<InboxPage />);
    await waitForList();

    act(() => setVisibility("hidden"));
    await act(() => vi.advanceTimersByTimeAsync(180_000));
    expect(calls).toBe(1);

    // More than a minute since the last fetch: refresh right away
    act(() => setVisibility("visible"));
    await act(() => vi.advanceTimersByTimeAsync(0));
    await waitFor(() => expect(calls).toBe(2));

    await act(() => vi.advanceTimersByTimeAsync(60_000));
    expect(calls).toBe(3);
  });

  it("switches from 5 s polls while scanning to 60 s after the scan ends", async () => {
    let calls = 0;
    server.use(
      http.get(SOURCES_URL, () => {
        calls += 1;
        return HttpResponse.json({
          ...mockVacancySourcesEmpty,
          sources: [{ ...mockVacancySource, scanning: calls < 3 }],
        });
      }),
    );
    renderWithProviders(<InboxPage />);
    expect(await screen.findByText("Telegram · Scanning…")).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(5_000));
    expect(calls).toBe(2);
    await act(() => vi.advanceTimersByTimeAsync(5_000));
    expect(calls).toBe(3);
    await waitFor(() =>
      expect(screen.queryByText("Telegram · Scanning…")).not.toBeInTheDocument(),
    );

    // Not scanning any more: no 5 s poll, only the 60 s one
    await act(() => vi.advanceTimersByTimeAsync(55_000));
    expect(calls).toBe(3);
    await act(() => vi.advanceTimersByTimeAsync(5_000));
    expect(calls).toBe(4);
  });

  it("stops the 60 s refresh on unmount", async () => {
    let calls = 0;
    server.use(
      http.get(SOURCES_URL, () => {
        calls += 1;
        return HttpResponse.json(mockVacancySourcesEmpty);
      }),
    );
    const { unmount } = renderWithProviders(<InboxPage />);
    await waitForList();

    unmount();
    setVisibility("visible");
    await act(() => vi.advanceTimersByTimeAsync(180_000));
    expect(calls).toBe(1);
  });
});

describe("Unavailable sources", () => {
  it("marks the source with its reason and keeps Remove available", async () => {
    server.use(
      http.get(SOURCES_URL, () =>
        HttpResponse.json({
          ...mockVacancySourcesEmpty,
          sources: [
            { ...mockVacancySource, id: "ok", display_name: "@fine_one" },
            {
              ...mockVacancySource,
              id: "gone",
              display_name: "@gone_board",
              unavailable: true,
              last_error: "Job board not found",
            },
            {
              ...mockVacancySource,
              id: "noreason",
              display_name: "@no_reason",
              unavailable: true,
              last_error: null,
            },
          ],
        }),
      ),
    );
    renderWithProviders(<InboxPage />);

    const list = await screen.findByRole("list", { name: "Watched sources" });
    const [fine, gone, noReason] = within(list).getAllByRole("listitem");
    expect(within(fine!).queryByText(/Unavailable/)).not.toBeInTheDocument();
    expect(within(gone!).getByText("Unavailable — Job board not found")).toBeInTheDocument();
    expect(within(gone!).getByRole("button", { name: "Remove @gone_board" })).toBeEnabled();
    expect(
      within(noReason!).getByText("Unavailable — Could not reach the source"),
    ).toBeInTheDocument();
    // Read in order: name, kind, then the reason
    expect(gone!.textContent).toBe("@gone_boardTelegramUnavailable — Job board not foundEditRemove");
  });
});

describe("Merged repost cards", () => {
  it("lists every channel after 'Posted in:' and keeps single-source cards as is", async () => {
    server.use(
      http.get(VACANCIES_URL, () =>
        HttpResponse.json({
          ...mockVacancyPageEmpty,
          items: [
            {
              ...mockVacancy,
              id: "merged",
              sources: [
                { key: "telegram:frontend_jobs", label: "@frontend_jobs" },
                { key: "telegram:react_jobs", label: "@react_jobs" },
              ],
            },
            { ...mockVacancy, id: "single", title: "Vue Developer" },
          ],
          total: 2,
        }),
      ),
    );
    renderWithProviders(<InboxPage />);

    const list = await screen.findByRole("list", { name: "Vacancies" });
    const [merged, single] = within(list).getAllByRole("article");
    expect(within(merged!).getByText(/^Posted in: @frontend_jobs, @react_jobs ·/)).toBeInTheDocument();
    expect(within(single!).queryByText(/Posted in:/)).not.toBeInTheDocument();
    expect(within(single!).getByText(/^@frontend_jobs ·/)).toBeInTheDocument();
  });
});
