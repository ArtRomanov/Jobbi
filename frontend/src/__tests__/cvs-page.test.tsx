import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CvsPage } from "@/pages/cvs/ui/cvs-page";
import { downloadCvTextPdf } from "@/features/cv-pdf";
import { http, HttpResponse } from "msw";
import { mockCvs } from "./mocks/handlers";
import { server } from "./setup";
import { renderWithProviders } from "./utils";

vi.mock("@/features/cv-pdf", () => ({ downloadCvTextPdf: vi.fn().mockResolvedValue(undefined) }));

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
});

describe("CvsPage", () => {
  it("announces a load error as an alert", async () => {
    server.use(
      http.get("*/api/v1/cvs", () => HttpResponse.json({ detail: "Boom" }, { status: 500 })),
    );
    renderWithProviders(<CvsPage />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("Software Engineer CV")).not.toBeInTheDocument();
  });

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

  it("exports a CV to PDF from its name and text", async () => {
    const user = userEvent.setup();
    renderWithProviders(<CvsPage />);

    await waitFor(() => {
      expect(screen.getByText("Software Engineer CV")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Export PDF: Software Engineer CV" }));

    expect(downloadCvTextPdf).toHaveBeenCalledWith({
      name: "Software Engineer CV",
      content: mockCvs[0]!.content,
    });
  });

  it('confirms a delete with the toast "CV deleted"', async () => {
    const user = userEvent.setup();
    window.confirm = vi.fn().mockReturnValue(true);
    let deleted: string | null = null;
    server.use(
      http.delete("*/api/v1/cvs/:id", ({ params }) => {
        deleted = params.id as string;
        return HttpResponse.json({ message: "CV deleted" });
      }),
    );
    renderWithProviders(<CvsPage />);
    await screen.findByText("Frontend Developer CV");

    await user.click(screen.getByRole("button", { name: "Delete Frontend Developer CV" }));

    expect(await screen.findByText("CV deleted")).toBeInTheDocument();
    expect(deleted).toBe("cv-2");
  });

  it('confirms a duplicate with the toast "CV duplicated"', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CvsPage />);
    await screen.findByText("Frontend Developer CV");

    await user.click(screen.getByRole("button", { name: "Duplicate Frontend Developer CV" }));

    expect(await screen.findByText("CV duplicated")).toBeInTheDocument();
  });
});
