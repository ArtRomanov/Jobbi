import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { ApplicationPanel } from "@/features/application-panel/ui/application-panel";
import { renderWithProviders } from "./utils";
import { server } from "./setup";
import { mockApplicationDetail, mockCvs } from "./mocks/handlers";

const noopClose = vi.fn();
const noopUpdate = vi.fn();

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
  noopClose.mockClear();
  noopUpdate.mockClear();
});

describe("ApplicationPanel — CV section", () => {
  it("shows the CV section in the panel with a linked CV", async () => {
    // Override the application detail to include a linked CV
    server.use(
      http.get("http://localhost:8000/api/v1/applications/:id", () => {
        return HttpResponse.json({
          ...mockApplicationDetail,
          cv_id: "cv-1",
          cv_name: "Software Engineer CV",
          status_history: mockApplicationDetail.status_history,
        });
      }),
    );

    renderWithProviders(
      <ApplicationPanel
        applicationId="app-1"
        onClose={noopClose}
        onUpdate={noopUpdate}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("CV")).toBeInTheDocument();
    });

    expect(
      screen.getByText("Linked: Software Engineer CV"),
    ).toBeInTheDocument();
  });

  it("lists own CVs first with the base labelled, then tailored copies in a group", async () => {
    // Shuffled on purpose: the panel groups by is_base / kind itself
    server.use(
      http.get("http://localhost:8000/api/v1/cvs", () =>
        HttpResponse.json([mockCvs[2], mockCvs[1], mockCvs[0]]),
      ),
    );

    renderWithProviders(
      <ApplicationPanel applicationId="app-1" onClose={noopClose} onUpdate={noopUpdate} />,
    );

    await screen.findByRole("option", { name: "Software Engineer CV (base)" });
    const select = screen.getByRole("option", { name: "None" }).closest("select")!;
    const ungrouped = Array.from(select.children)
      .filter((el) => el.tagName === "OPTION")
      .map((el) => el.textContent);
    expect(ungrouped).toEqual(["None", "Software Engineer CV (base)", "Frontend Developer CV"]);
    const group = select.querySelector("optgroup");
    expect(group).toHaveAttribute("label", "Tailored copies");
    expect(within(group!).getByRole("option", { name: mockCvs[2]!.name })).toHaveValue("cv-3");
  });

  it("shows 'No CV linked' when cv_id is null", async () => {
    // Override the application detail with no CV linked
    server.use(
      http.get("http://localhost:8000/api/v1/applications/:id", () => {
        return HttpResponse.json({
          ...mockApplicationDetail,
          cv_id: null,
          cv_name: null,
          status_history: mockApplicationDetail.status_history,
        });
      }),
    );

    renderWithProviders(
      <ApplicationPanel
        applicationId="app-1"
        onClose={noopClose}
        onUpdate={noopUpdate}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("No CV linked")).toBeInTheDocument();
    });
  });

  it('"Duplicate & Customize" confirms with the toast "CV duplicated"', async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/applications/:id", () =>
        HttpResponse.json({
          ...mockApplicationDetail,
          cv_id: "cv-1",
          cv_name: "Software Engineer CV",
          status_history: mockApplicationDetail.status_history,
        }),
      ),
    );
    const { router } = renderWithProviders(
      <ApplicationPanel applicationId="app-1" onClose={noopClose} onUpdate={noopUpdate} />,
    );

    const button = await screen.findByRole("button", { name: /duplicate & customize/i });
    button.click();

    expect(await screen.findByText("CV duplicated")).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.pathname).toBe("/cvs/cv-duplicated/edit"));
  });
});
