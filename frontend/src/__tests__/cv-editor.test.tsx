import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CvEditorForm } from "@/features/cv-editor/ui/cv-editor-form";
import { renderWithProviders } from "./utils";

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
});

describe("CvEditorForm", () => {
  const noopSave = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    noopSave.mockClear();
  });

  it("renders the name input and section labels", () => {
    renderWithProviders(
      <CvEditorForm onSave={noopSave} isSaving={false} />,
    );

    // CV Name input field
    expect(screen.getByLabelText(/cv name/i)).toBeInTheDocument();

    // Section divider labels
    expect(screen.getByText("Personal Information")).toBeInTheDocument();
    expect(screen.getByText("Summary")).toBeInTheDocument();
    expect(screen.getByText("Work Experience")).toBeInTheDocument();
    expect(screen.getByText("Education")).toBeInTheDocument();
    expect(screen.getByText("Skills & Languages")).toBeInTheDocument();
  });

  it("adds a new work experience entry when clicking Add", async () => {
    const user = userEvent.setup();

    renderWithProviders(
      <CvEditorForm onSave={noopSave} isSaving={false} />,
    );

    // Initially no experience entries
    expect(screen.queryByText("Experience 1")).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: /add work experience/i }),
    );

    // After clicking, the first entry appears
    expect(screen.getByText("Experience 1")).toBeInTheDocument();
    expect(screen.getByLabelText(/company/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^role$/i)).toBeInTheDocument();
  });

  it("calls onSave with form data when submitted with a valid name", async () => {
    const user = userEvent.setup();

    renderWithProviders(
      <CvEditorForm onSave={noopSave} isSaving={false} />,
    );

    const nameInput = screen.getByLabelText(/cv name/i);
    await user.type(nameInput, "My New CV");

    await user.click(screen.getByRole("button", { name: /save cv/i }));

    await waitFor(() => {
      expect(noopSave).toHaveBeenCalledTimes(1);
    });

    expect(noopSave).toHaveBeenCalledWith(
      expect.objectContaining({ name: "My New CV" }),
      expect.anything(),
    );
  });
});
