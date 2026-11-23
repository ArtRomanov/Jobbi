import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { CvsPage } from "@/pages/cvs";
import type { Cv } from "@/entities/cv";
import { makeMockCv, mockCvs } from "./mocks/handlers";
import { server } from "./setup";
import { renderWithProviders } from "./utils";

vi.mock("@/features/cv-pdf", () => ({ downloadCvTextPdf: vi.fn().mockResolvedValue(undefined) }));

const CVS_URL = "*/api/v1/cvs";
const MAKE_BASE_URL = "*/api/v1/cvs/:id/make-base";
const NO_BASE_HINT = 'Mark one of your CVs as base — "Add & tailor CV" will start from it.';

function serveCvs(cvs: Cv[]): void {
  server.use(http.get(CVS_URL, () => HttpResponse.json(cvs)));
}

function section(name: string): HTMLElement {
  return screen.getByRole("region", { name });
}

/** Row names in a section, in order. */
function rowNames(region: HTMLElement): string[] {
  return within(region)
    .getAllByRole("listitem")
    .map((item) => item.querySelector("span")?.textContent ?? "");
}

function rowOf(name: string): HTMLElement {
  return screen.getByText(name, { selector: "span" }).closest("li")!;
}

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
});

describe("CVs page — My CVs and Tailored for applications", () => {
  it("shows the base first with a Base label, other own CVs, then tailored copies", async () => {
    // Shuffled on purpose: the page groups by is_base / kind itself
    serveCvs([mockCvs[2]!, mockCvs[1]!, mockCvs[0]!]);
    renderWithProviders(<CvsPage />);

    const mine = await screen.findByRole("region", { name: "My CVs" });
    expect(rowNames(mine)).toEqual(["Software Engineer CV", "Frontend Developer CV"]);
    expect(within(rowOf("Software Engineer CV")).getByText("Base")).toBeInTheDocument();
    expect(within(rowOf("Frontend Developer CV")).queryByText("Base")).not.toBeInTheDocument();

    const tailored = section("Tailored for applications");
    expect(rowNames(tailored)).toEqual([mockCvs[2]!.name]);
    expect(screen.queryByText(NO_BASE_HINT)).not.toBeInTheDocument();
  });

  it("links a tailored copy to its application on the dashboard", async () => {
    renderWithProviders(<CvsPage />);

    const tailored = await screen.findByRole("region", { name: "Tailored for applications" });
    const link = within(tailored).getByRole("link", { name: "Acme Corp — Senior Engineer" });
    expect(link).toHaveAttribute("href", "/dashboard?application=app-1");
  });

  it("shows Application deleted instead of a link when the application is gone", async () => {
    serveCvs([
      mockCvs[0]!,
      makeMockCv({
        id: "cv-orphan",
        name: "Old copy",
        kind: "tailored",
        tailored_for: { application_id: "app-gone", company_name: "Kleos", role_title: "Dev" },
        tailored_application_deleted: true,
      }),
    ]);
    renderWithProviders(<CvsPage />);

    const tailored = await screen.findByRole("region", { name: "Tailored for applications" });
    expect(within(tailored).getByText("Application deleted")).toBeInTheDocument();
    expect(within(tailored).queryByRole("link", { name: /Kleos/ })).not.toBeInTheDocument();
  });

  it("hides the tailored section when there are no tailored copies", async () => {
    serveCvs(mockCvs.slice(0, 2));
    renderWithProviders(<CvsPage />);

    await screen.findByRole("region", { name: "My CVs" });
    expect(screen.queryByRole("region", { name: "Tailored for applications" })).not.toBeInTheDocument();
  });

  it("with no CVs shows the empty text under My CVs, and no hint", async () => {
    serveCvs([]);
    renderWithProviders(<CvsPage />);

    const mine = await screen.findByRole("region", { name: "My CVs" });
    expect(within(mine).getByText("No CVs yet. Upload your CV or create one.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Tailored for applications" })).not.toBeInTheDocument();
    expect(screen.queryByText(NO_BASE_HINT)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload CV" })).toBeInTheDocument();
  });

  it("shows the no-base hint above My CVs when there are CVs but no base", async () => {
    serveCvs(mockCvs.map((cv) => ({ ...cv, is_base: false })));
    renderWithProviders(<CvsPage />);

    const hint = await screen.findByText(NO_BASE_HINT);
    const mine = section("My CVs");
    expect(mine.contains(hint)).toBe(false);
    // The hint comes before the section in document order
    expect(hint.compareDocumentPosition(mine) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByText("Base")).not.toBeInTheDocument();
  });

  it("keeps open, duplicate, PDF and delete on tailored copies too", async () => {
    renderWithProviders(<CvsPage />);

    await screen.findByRole("region", { name: "Tailored for applications" });
    const cvName = mockCvs[2]!.name;
    const row = rowOf(cvName);
    expect(within(row).getByRole("link", { name: `Edit ${cvName}` })).toHaveAttribute("href", "/cvs/cv-3/edit");
    for (const name of [`Duplicate ${cvName}`, `Export PDF: ${cvName}`, `Delete ${cvName}`]) {
      expect(within(row).getByRole("button", { name })).toBeInTheDocument();
    }
  });

  it("renders Edit as a single link (no button inside it) with short visible text", async () => {
    renderWithProviders(<CvsPage />);

    await screen.findByRole("region", { name: "My CVs" });
    const row = rowOf("Software Engineer CV");
    const edit = within(row).getByRole("link", { name: "Edit Software Engineer CV" });
    expect(edit).toHaveTextContent(/^Edit$/);
    expect(edit.querySelector("button")).toBeNull();
    expect(within(row).getByRole("button", { name: "Export PDF: Software Engineer CV" })).toHaveTextContent(/^PDF$/);
  });

  it("gives every row action a unique accessible name", async () => {
    renderWithProviders(<CvsPage />);

    await screen.findByRole("region", { name: "My CVs" });
    for (const label of ["Edit", "Duplicate", "Export PDF:", "Delete"]) {
      const role = label === "Edit" ? "link" : "button";
      const names = screen
        .getAllByRole(role, { name: new RegExp(`^${label} `) })
        .map((el) => el.getAttribute("aria-label"));
      expect(names).toHaveLength(mockCvs.length);
      expect(new Set(names).size).toBe(names.length);
    }
  });
});

describe("CVs page — Make base", () => {
  it("offers Make base on every CV except the base", async () => {
    renderWithProviders(<CvsPage />);

    await screen.findByRole("region", { name: "My CVs" });
    expect(within(rowOf("Software Engineer CV")).queryByRole("button", { name: /^Make base/ })).toBeNull();
    expect(
      within(rowOf("Frontend Developer CV")).getByRole("button", { name: "Make base: Frontend Developer CV" }),
    ).toBeInTheDocument();
    expect(within(rowOf(mockCvs[2]!.name)).getByRole("button", { name: /^Make base/ })).toBeInTheDocument();
  });

  it("makes a tailored copy the base, shows the toast and refreshes the list", async () => {
    const user = userEvent.setup();
    const madeBase: string[] = [];
    let current: Cv[] = mockCvs;
    server.use(
      http.get(CVS_URL, () => HttpResponse.json(current)),
      http.post(MAKE_BASE_URL, ({ params }) => {
        madeBase.push(String(params.id));
        const promoted = { ...mockCvs[2]!, is_base: true, kind: "own" as const };
        current = [promoted, { ...mockCvs[0]!, is_base: false }, mockCvs[1]!];
        return HttpResponse.json(promoted);
      }),
    );
    renderWithProviders(<CvsPage />);

    await screen.findByRole("region", { name: "Tailored for applications" });
    await user.click(screen.getByRole("button", { name: `Make base: ${mockCvs[2]!.name}` }));

    expect(await screen.findByText("Base CV updated")).toBeInTheDocument();
    expect(madeBase).toEqual(["cv-3"]);
    await waitFor(() =>
      expect(rowNames(section("My CVs"))).toEqual([
        mockCvs[2]!.name,
        "Frontend Developer CV",
        "Software Engineer CV",
      ]),
    );
    expect(screen.queryByRole("region", { name: "Tailored for applications" })).not.toBeInTheDocument();
    expect(within(rowOf(mockCvs[2]!.name)).getByText("Base")).toBeInTheDocument();
  });

  it("shows an error toast and keeps the list when make-base fails", async () => {
    const user = userEvent.setup();
    server.use(http.post(MAKE_BASE_URL, () => HttpResponse.json({ detail: "CV not found." }, { status: 404 })));
    renderWithProviders(<CvsPage />);

    await screen.findByRole("region", { name: "My CVs" });
    await user.click(screen.getByRole("button", { name: "Make base: Frontend Developer CV" }));

    expect(await screen.findByText("CV not found.")).toBeInTheDocument();
    expect(screen.queryByText("Base CV updated")).not.toBeInTheDocument();
    expect(within(rowOf("Software Engineer CV")).getByText("Base")).toBeInTheDocument();
  });
});

describe("CVs page — refreshing the list", () => {
  it("ignores an older refresh that answers after a newer one", async () => {
    const user = userEvent.setup();
    const stale = mockCvs.map((cv) => ({ ...cv, name: `${cv.name} (stale)` }));
    const fresh = mockCvs.map((cv) => (cv.id === "cv-2" ? { ...cv, name: "Fresh name" } : cv));
    let calls = 0;
    server.use(
      http.get(CVS_URL, async () => {
        calls += 1;
        if (calls === 2) {
          // The first refresh is slow and must lose to the second
          await delay(150);
          return HttpResponse.json(stale);
        }
        return HttpResponse.json(calls === 1 ? mockCvs : fresh);
      }),
    );
    renderWithProviders(<CvsPage />);

    await screen.findByRole("region", { name: "My CVs" });
    await user.click(screen.getByRole("button", { name: "Make base: Frontend Developer CV" }));
    await waitFor(() => expect(calls).toBe(2));
    await user.click(screen.getByRole("button", { name: `Make base: ${mockCvs[2]!.name}` }));

    expect(await screen.findByText("Fresh name")).toBeInTheDocument();
    // Let the slow response land; it must not replace the newer list
    await new Promise((resolve) => setTimeout(resolve, 250));
    expect(calls).toBe(3);
    expect(screen.getByText("Fresh name")).toBeInTheDocument();
    expect(screen.queryByText(/\(stale\)/)).not.toBeInTheDocument();
  });

  it("keeps the list and shows a toast when a refresh fails", async () => {
    const user = userEvent.setup();
    let calls = 0;
    server.use(
      http.get(CVS_URL, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json(mockCvs)
          : HttpResponse.json({ detail: "Server is down." }, { status: 500 });
      }),
    );
    renderWithProviders(<CvsPage />);

    await screen.findByRole("region", { name: "My CVs" });
    await user.click(screen.getByRole("button", { name: "Make base: Frontend Developer CV" }));

    await waitFor(() => expect(calls).toBe(2));
    expect(await screen.findByText("Base CV updated")).toBeInTheDocument();
    expect(
      await screen.findByText("Could not refresh your CVs. Reload the page to see the latest list."),
    ).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "My CVs" })).toBeInTheDocument();
    expect(rowNames(section("My CVs"))).toEqual(["Software Engineer CV", "Frontend Developer CV"]);
    expect(screen.getByRole("region", { name: "Tailored for applications" })).toBeInTheDocument();
  });

  it("shows the error in place of the list when the first load fails", async () => {
    server.use(http.get(CVS_URL, () => HttpResponse.json({ detail: "x" }, { status: 500 })));
    renderWithProviders(<CvsPage />);

    expect(await screen.findByText(/Request failed/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "My CVs" })).not.toBeInTheDocument();
  });
});
