import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DashboardPage } from "@/pages/dashboard";
import { renderWithProviders } from "./utils";

describe("DashboardPage view toggle", () => {
  it("starts on Board and switches to Timeline with the segmented control", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DashboardPage />);

    expect(screen.getByRole("radiogroup", { name: "Dashboard view" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Board" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("textbox", { name: "Search applications" })).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "Timeline" }));

    expect(screen.getByRole("radio", { name: "Timeline" })).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByRole("textbox", { name: "Search applications" })).not.toBeInTheDocument();
  });

  it("switches views with the arrow keys", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DashboardPage />);

    screen.getByRole("radio", { name: "Board" }).focus();
    await user.keyboard("{ArrowRight}");

    expect(screen.getByRole("radio", { name: "Timeline" })).toHaveFocus();
    expect(screen.queryByRole("group", { name: "Column visibility" })).not.toBeInTheDocument();

    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("radio", { name: "Board" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("group", { name: "Column visibility" })).toBeInTheDocument();
  });
});
