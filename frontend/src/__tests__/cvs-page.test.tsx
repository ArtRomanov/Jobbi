import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CvsPage } from "@/pages/cvs/ui/cvs-page";
import { renderWithProviders } from "./utils";

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
});

describe("CvsPage", () => {
  it("renders the CV list with CV names visible", async () => {
    renderWithProviders(<CvsPage />);

    await waitFor(() => {
      expect(screen.getByText("Software Engineer CV")).toBeInTheDocument();
    });

    expect(screen.getByText("Frontend Developer CV")).toBeInTheDocument();
  });

  it("shows the Create New CV link", async () => {
    renderWithProviders(<CvsPage />);

    await waitFor(() => {
      expect(screen.getByText("Software Engineer CV")).toBeInTheDocument();
    });

    const link = screen.getByRole("link", { name: /create new cv/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/cvs/new");
  });

  it("shows a confirmation dialog when delete is clicked", async () => {
    const user = userEvent.setup();

    // happy-dom does not define window.confirm by default, so assign a mock
    const confirmMock = vi.fn().mockReturnValue(false);
    window.confirm = confirmMock;

    renderWithProviders(<CvsPage />);

    await waitFor(() => {
      expect(screen.getByText("Software Engineer CV")).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByRole("button", { name: /delete/i });
    const firstDeleteButton = deleteButtons[0]!;
    await user.click(firstDeleteButton);

    expect(confirmMock).toHaveBeenCalledWith(
      expect.stringContaining("Software Engineer CV"),
    );
  });
});
