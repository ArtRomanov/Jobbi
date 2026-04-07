import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DateRangeSelector } from "@/features/metrics-dashboard";
import { renderWithProviders } from "./utils";

describe("DateRangeSelector", () => {
  it("renders all four range option buttons", () => {
    renderWithProviders(
      <DateRangeSelector value="30d" onChange={() => undefined} />,
    );

    expect(
      screen.getByRole("button", { name: "Last 7 days" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Last 30 days" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Last 90 days" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "All time" }),
    ).toBeInTheDocument();
  });

  it("marks the active button with aria-pressed=true", () => {
    renderWithProviders(
      <DateRangeSelector value="30d" onChange={() => undefined} />,
    );

    const active = screen.getByRole("button", { name: "Last 30 days" });
    expect(active).toHaveAttribute("aria-pressed", "true");

    const inactive = screen.getByRole("button", { name: "Last 7 days" });
    expect(inactive).toHaveAttribute("aria-pressed", "false");
  });

  it("calls onChange with the option value when a button is clicked", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderWithProviders(
      <DateRangeSelector value="30d" onChange={onChange} />,
    );

    await user.click(screen.getByRole("button", { name: "Last 7 days" }));

    expect(onChange).toHaveBeenCalledWith("7d");
  });
});
