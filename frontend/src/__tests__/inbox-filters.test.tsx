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

/** Serves one card per request and records each request's query. */
function recordListRequests(): URLSearchParams[] {
  const requests: URLSearchParams[] = [];
  server.use(
    http.get(VACANCIES_URL, ({ request }) => {
      requests.push(new URL(request.url).searchParams);
      return HttpResponse.json({ ...mockVacancyPageEmpty, items: [mockVacancy], total: 1 });
    }),
  );
  return requests;
}

function serveSources(): void {
  server.use(
    http.get(SOURCES_URL, () =>
      HttpResponse.json({
        ...mockVacancySourcesEmpty,
        sources: [
          mockVacancySource,
          {
            ...mockVacancySource,
            id: "src-2",
            key: "greenhouse:acme",
            kind: "greenhouse",
            display_name: "Acme",
          },
        ],
        removed_sources: [
          { key: "telegram:old_jobs", label: "@old_jobs" },
          { key: "tg_forward:c1234567890", label: "Secret Jobs" },
        ],
      }),
    ),
  );
}

async function renderInbox() {
  const user = userEvent.setup();
  renderWithProviders(<InboxPage />);
  await screen.findByRole("heading", { name: "Senior React Developer" });
  return user;
}

describe("Inbox filters", () => {
  it("lists all sources, live sources, removed (removed) and forwarded (forwarded) sources", async () => {
    serveSources();
    recordListRequests();
    await renderInbox();

    const select = screen.getByRole("combobox", { name: "Source" });
    await waitFor(() => expect(within(select).getAllByRole("option")).toHaveLength(5));
    const options = within(select)
      .getAllByRole("option")
      .map((option) => [option.getAttribute("value"), option.textContent]);
    expect(options).toEqual([
      ["", "All sources"],
      ["telegram:frontend_jobs", "@frontend_jobs"],
      ["greenhouse:acme", "Acme"],
      ["telegram:old_jobs", "@old_jobs (removed)"],
      ["tg_forward:c1234567890", "Secret Jobs (forwarded)"],
    ]);
  });

  it("starts with all sources, all states, newest first", async () => {
    const requests = recordListRequests();
    await renderInbox();

    expect(screen.getByRole("combobox", { name: "Source" })).toHaveValue("");
    expect(screen.getByRole("radio", { name: "All" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "Newest" })).toHaveAttribute("aria-checked", "true");
    expect(requests[0]?.get("source")).toBeNull();
    expect(requests[0]?.get("state")).toBe("all");
    expect(requests[0]?.get("sort")).toBe("date");
    expect(requests[0]?.get("page")).toBe("1");
  });

  it("combines source, state and sort and reloads page 1 on every change", async () => {
    serveSources();
    const requests = recordListRequests();
    const user = await renderInbox();
    const select = screen.getByRole("combobox", { name: "Source" });
    await waitFor(() => expect(within(select).getAllByRole("option")).toHaveLength(5));

    await user.selectOptions(select, "telegram:old_jobs");
    await waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[1]?.get("source")).toBe("telegram:old_jobs");
    expect(requests[1]?.get("state")).toBe("all");

    await user.click(screen.getByRole("radio", { name: "New" }));
    await waitFor(() => expect(requests).toHaveLength(3));
    expect(requests[2]?.get("source")).toBe("telegram:old_jobs");
    expect(requests[2]?.get("state")).toBe("new");
    expect(requests[2]?.get("sort")).toBe("date");

    await user.click(screen.getByRole("radio", { name: "Best fit" }));
    await waitFor(() => expect(requests).toHaveLength(4));
    expect(requests[3]?.get("source")).toBe("telegram:old_jobs");
    expect(requests[3]?.get("state")).toBe("new");
    expect(requests[3]?.get("sort")).toBe("fit");
    expect(requests[3]?.get("page")).toBe("1");

    await user.selectOptions(select, "");
    await waitFor(() => expect(requests).toHaveLength(5));
    expect(requests[4]?.get("source")).toBeNull();
    expect(requests[4]?.get("state")).toBe("new");
    expect(requests[4]?.get("sort")).toBe("fit");
  });

  it("uses the current filters for Load more", async () => {
    const requests: URLSearchParams[] = [];
    server.use(
      http.get(VACANCIES_URL, ({ request }) => {
        const params = new URL(request.url).searchParams;
        requests.push(params);
        const isSecondPage = params.get("page") === "2";
        return HttpResponse.json({
          ...mockVacancyPageEmpty,
          items: [isSecondPage ? { ...mockVacancy, id: "vac-2", title: "Page two" } : mockVacancy],
          total: 2,
        });
      }),
    );
    const user = await renderInbox();

    await user.click(screen.getByRole("radio", { name: "Seen" }));
    await waitFor(() => expect(requests).toHaveLength(2));
    await screen.findByRole("button", { name: "Load more" });
    await user.click(screen.getByRole("button", { name: "Load more" }));

    expect(await screen.findByRole("heading", { name: "Page two" })).toBeInTheDocument();
    expect(requests[2]?.get("page")).toBe("2");
    expect(requests[2]?.get("state")).toBe("seen");
  });

  it("says no vacancies match when filters leave the list empty", async () => {
    server.use(
      http.get(VACANCIES_URL, ({ request }) => {
        const state = new URL(request.url).searchParams.get("state");
        return HttpResponse.json(
          state === "new"
            ? mockVacancyPageEmpty
            : { ...mockVacancyPageEmpty, items: [mockVacancy], total: 1 },
        );
      }),
    );
    const user = await renderInbox();

    await user.click(screen.getByRole("radio", { name: "New" }));

    expect(await screen.findByText("No vacancies match these filters.")).toBeInTheDocument();
    expect(screen.queryByText("No vacancies yet.")).not.toBeInTheDocument();
  });

  it("marks a source (removed) after the user removes it while its cards remain", async () => {
    let isRemoved = false;
    server.use(
      http.get(SOURCES_URL, () =>
        HttpResponse.json({
          ...mockVacancySourcesEmpty,
          sources: isRemoved ? [] : [mockVacancySource],
          removed_sources: isRemoved
            ? [{ key: mockVacancySource.key, label: mockVacancySource.display_name }]
            : [],
        }),
      ),
      http.delete("*/api/v1/vacancy-sources/:id", () => {
        isRemoved = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    recordListRequests();
    const user = await renderInbox();
    const select = screen.getByRole("combobox", { name: "Source" });
    expect(await within(select).findByRole("option", { name: "@frontend_jobs" })).toBeInTheDocument();

    const sources = screen.getByRole("list", { name: "Watched sources" });
    await user.click(within(sources).getByRole("button", { name: /Remove/ }));

    expect(
      await within(select).findByRole("option", { name: "@frontend_jobs (removed)" }),
    ).toBeInTheDocument();
    expect(within(select).queryByRole("option", { name: "@frontend_jobs" })).not.toBeInTheDocument();
  });

  it("starts filtered by the source in ?source= (link from the Telegram first-scan summary)", async () => {
    server.use(
      http.get(SOURCES_URL, () =>
        HttpResponse.json({
          ...mockVacancySourcesEmpty,
          sources: [{ ...mockVacancySource, id: "src-r", key: "telegram:relocats", display_name: "IT Relocation" }],
        }),
      ),
    );
    const requests = recordListRequests();
    renderWithProviders(<InboxPage />, { initialEntries: ["/inbox?source=telegram%3Arelocats"] });
    await screen.findByRole("heading", { name: "Senior React Developer" });

    expect(requests[0]?.get("source")).toBe("telegram:relocats");
    const select = screen.getByRole("combobox", { name: "Source" });
    expect(select).toHaveValue("telegram:relocats");
    expect(await within(select).findByRole("option", { name: "IT Relocation" })).toBeInTheDocument();
    expect(within(select).getAllByRole("option", { selected: true }).map((option) => option.textContent)).toEqual([
      "IT Relocation",
    ]);
  });

  it("keeps a ?source= key that is not in the source list selectable", async () => {
    const requests = recordListRequests();
    renderWithProviders(<InboxPage />, { initialEntries: ["/inbox?source=telegram:gone_channel"] });
    await screen.findByRole("heading", { name: "Senior React Developer" });

    expect(requests[0]?.get("source")).toBe("telegram:gone_channel");
    const select = screen.getByRole("combobox", { name: "Source" });
    expect(select).toHaveValue("telegram:gone_channel");
    expect(within(select).getByRole("option", { name: "telegram:gone_channel (removed)" })).toBeInTheDocument();
  });

  it("ignores an empty ?source=", async () => {
    const requests = recordListRequests();
    renderWithProviders(<InboxPage />, { initialEntries: ["/inbox?source="] });
    await screen.findByRole("heading", { name: "Senior React Developer" });

    expect(requests[0]?.get("source")).toBeNull();
    expect(screen.getByRole("combobox", { name: "Source" })).toHaveValue("");
  });
});
