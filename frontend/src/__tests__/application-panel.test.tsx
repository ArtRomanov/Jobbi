import { screen, waitFor } from "@testing-library/react";
import { ApplicationPanel } from "@/features/application-panel/ui/application-panel";
import { renderWithProviders } from "./utils";

const noopClose = vi.fn();
const noopUpdate = vi.fn();

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
  noopClose.mockClear();
  noopUpdate.mockClear();
});

describe("ApplicationPanel", () => {
  it("renders when applicationId is set", async () => {
    renderWithProviders(
      <ApplicationPanel
        applicationId="app-1"
        onClose={noopClose}
        onUpdate={noopUpdate}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("dialog", { name: /application details/i }),
      ).toBeInTheDocument();
    });
  });

  it("is hidden when applicationId is null", () => {
    renderWithProviders(
      <ApplicationPanel
        applicationId={null}
        onClose={noopClose}
        onUpdate={noopUpdate}
      />,
    );

    expect(
      screen.queryByRole("dialog", { name: /application details/i }),
    ).not.toBeInTheDocument();
  });

  it("displays application fields from mock data", async () => {
    renderWithProviders(
      <ApplicationPanel
        applicationId="app-1"
        onClose={noopClose}
        onUpdate={noopUpdate}
      />,
    );

    // Wait for the detail to load — company name appears in the form input
    await waitFor(() => {
      expect(screen.getByDisplayValue("Acme Corp")).toBeInTheDocument();
    });

    expect(screen.getByDisplayValue("Senior Engineer")).toBeInTheDocument();
    expect(
      screen.getByDisplayValue("https://acme.com/jobs/1"),
    ).toBeInTheDocument();
    expect(screen.getByDisplayValue("100000")).toBeInTheDocument();
    expect(screen.getByDisplayValue("150000")).toBeInTheDocument();
    expect(screen.getByDisplayValue("USD")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Alice HR")).toBeInTheDocument();
    expect(screen.getByDisplayValue("alice@acme.com")).toBeInTheDocument();
  });

  it("displays status history entries", async () => {
    renderWithProviders(
      <ApplicationPanel
        applicationId="app-1"
        onClose={noopClose}
        onUpdate={noopUpdate}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Status History")).toBeInTheDocument();
    });

    // The mock has two history entries: "researching" and "applied".
    // Status labels also appear in the <select> options, so we scope to
    // the <strong> elements rendered inside the history list.
    const historyLabels = screen.getAllByRole("listitem");
    expect(historyLabels).toHaveLength(2);
    expect(historyLabels[0]).toHaveTextContent("Researching");
    expect(historyLabels[1]).toHaveTextContent("Applied");
  });
});
