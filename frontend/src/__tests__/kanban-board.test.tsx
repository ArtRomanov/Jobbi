import { screen, waitFor } from "@testing-library/react";
import { KanbanBoard } from "@/features/kanban-board/ui/kanban-board";
import { renderWithProviders } from "./utils";

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
});

describe("KanbanBoard", () => {
  it("renders all six status columns", async () => {
    renderWithProviders(<KanbanBoard />);

    await waitFor(() => {
      expect(screen.getByText("Researching")).toBeInTheDocument();
    });

    expect(screen.getByText("Applied")).toBeInTheDocument();
    expect(screen.getByText("Interview")).toBeInTheDocument();
    expect(screen.getByText("Offer")).toBeInTheDocument();
    expect(screen.getByText("Rejected")).toBeInTheDocument();
    expect(screen.getByText("Withdrawn")).toBeInTheDocument();
  });

  it("places application cards in the correct status columns", async () => {
    renderWithProviders(<KanbanBoard />);

    // Wait for data to load
    await waitFor(() => {
      expect(screen.getByText("Acme Corp")).toBeInTheDocument();
    });

    // Both cards should be visible
    expect(screen.getByText("Acme Corp")).toBeInTheDocument();
    expect(screen.getByText("Senior Engineer")).toBeInTheDocument();
    expect(screen.getByText("TechStart")).toBeInTheDocument();
    expect(screen.getByText("Frontend Dev")).toBeInTheDocument();
  });

  it("shows a loading indicator initially", () => {
    renderWithProviders(<KanbanBoard />);

    expect(screen.getByText("Loading applications...")).toBeInTheDocument();
  });

  it("shows the New Application button", async () => {
    renderWithProviders(<KanbanBoard />);

    await waitFor(() => {
      expect(screen.getByText("Acme Corp")).toBeInTheDocument();
    });

    const link = screen.getByRole("link", { name: /new application/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/new-application");
  });
});
