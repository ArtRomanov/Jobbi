import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QuickActionBar } from "@/features/chat-interface";
import { QUICK_ACTIONS } from "@/features/chat-interface";
import { renderWithProviders } from "./utils";

const mockOnAction = vi.fn();

beforeEach(() => {
  mockOnAction.mockClear();
});

describe("QuickActionBar", () => {
  it("renders three quick action buttons", () => {
    renderWithProviders(
      <QuickActionBar
        onAction={mockOnAction}
        hasCv
        companyName="Acme Corp"
        roleTitle="Senior Engineer"
      />,
    );

    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(3);
    expect(screen.getByText("Refine my CV")).toBeInTheDocument();
    expect(screen.getByText("Write a cover letter")).toBeInTheDocument();
    expect(screen.getByText("Prep for interview")).toBeInTheDocument();
  });

  it("disables 'Refine my CV' when hasCv is false", () => {
    renderWithProviders(
      <QuickActionBar
        onAction={mockOnAction}
        hasCv={false}
        companyName="Acme Corp"
        roleTitle="Senior Engineer"
      />,
    );

    const refineButton = screen.getByText("Refine my CV");
    expect(refineButton).toBeDisabled();
    expect(refineButton).toHaveAttribute(
      "title",
      "Link a CV to this application first",
    );
  });

  it("enables 'Refine my CV' when hasCv is true", () => {
    renderWithProviders(
      <QuickActionBar
        onAction={mockOnAction}
        hasCv
        companyName="Acme Corp"
        roleTitle="Senior Engineer"
      />,
    );

    const refineButton = screen.getByText("Refine my CV");
    expect(refineButton).toBeEnabled();
  });

  it("calls onAction with a filled template when a button is clicked", async () => {
    const user = userEvent.setup();

    renderWithProviders(
      <QuickActionBar
        onAction={mockOnAction}
        hasCv
        companyName="Acme Corp"
        roleTitle="Senior Engineer"
      />,
    );

    await user.click(screen.getByText("Write a cover letter"));

    const coverLetterAction = QUICK_ACTIONS.find(
      (a) => a.id === "cover-letter",
    )!;
    const expected = coverLetterAction.template
      .replace("{company_name}", "Acme Corp")
      .replace("{role_title}", "Senior Engineer");

    expect(mockOnAction).toHaveBeenCalledTimes(1);
    expect(mockOnAction).toHaveBeenCalledWith(expected);
  });
});
