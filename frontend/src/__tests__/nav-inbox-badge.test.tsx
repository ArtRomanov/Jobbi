import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Layout } from "@/app/layout";
import { notifyVacanciesChanged } from "@/entities/vacancy";
import { ToastProvider } from "@/shared/ui";
import { server } from "./setup";

const NEW_COUNT_URL = "*/api/v1/vacancies/new-count";

function renderLayout(): void {
  render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <ToastProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/dashboard" element={<p>Dashboard page</p>} />
            <Route path="/cvs" element={<p>CVs page</p>} />
          </Route>
        </Routes>
      </ToastProvider>
    </MemoryRouter>,
  );
}

/** Serves counts in order; the last one repeats. Returns the call counter. */
function serveCounts(counts: number[]): { calls: () => number } {
  let calls = 0;
  server.use(
    http.get(NEW_COUNT_URL, () => {
      const count = counts[Math.min(calls, counts.length - 1)] ?? 0;
      calls += 1;
      return HttpResponse.json({ count });
    }),
  );
  return { calls: () => calls };
}

describe("Inbox nav badge", () => {
  it("shows the new count with an accessible label", async () => {
    serveCounts([3]);
    renderLayout();

    const link = await screen.findByRole("link", { name: "Inbox, 3 new" });
    expect(link).toHaveAttribute("href", "/inbox");
    expect(link).toHaveTextContent("3");
  });

  it("hides the badge when the count is 0", async () => {
    const counter = serveCounts([0]);
    renderLayout();

    await waitFor(() => expect(counter.calls()).toBe(1));
    const link = screen.getByRole("link", { name: "Inbox" });
    expect(link).toHaveTextContent(/^Inbox$/);
  });

  it("refetches on notifyVacanciesChanged", async () => {
    serveCounts([2, 5]);
    renderLayout();
    expect(await screen.findByRole("link", { name: "Inbox, 2 new" })).toBeInTheDocument();

    act(() => notifyVacanciesChanged());

    expect(await screen.findByRole("link", { name: "Inbox, 5 new" })).toBeInTheDocument();
  });

  it("refetches on route change and hides the badge when it drops to 0", async () => {
    const counter = serveCounts([1, 0]);
    const user = userEvent.setup();
    renderLayout();
    expect(await screen.findByRole("link", { name: "Inbox, 1 new" })).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "CVs" }));

    expect(await screen.findByText("CVs page")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("link", { name: "Inbox" })).toBeInTheDocument());
    expect(counter.calls()).toBe(2);
  });

  it("keeps the last count when a refetch fails", async () => {
    let calls = 0;
    server.use(
      http.get(NEW_COUNT_URL, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ count: 4 })
          : HttpResponse.json({ detail: "boom" }, { status: 500 });
      }),
    );
    renderLayout();
    expect(await screen.findByRole("link", { name: "Inbox, 4 new" })).toBeInTheDocument();

    act(() => notifyVacanciesChanged());

    await waitFor(() => expect(calls).toBe(2));
    expect(screen.getByRole("link", { name: "Inbox, 4 new" })).toBeInTheDocument();
  });
});
