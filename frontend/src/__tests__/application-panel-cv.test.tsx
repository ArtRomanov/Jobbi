import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { ApplicationPanel } from "@/features/application-panel/ui/application-panel";
import { renderWithProviders } from "./utils";
import { server } from "./setup";
import { mockApplicationDetail } from "./mocks/handlers";

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
});
