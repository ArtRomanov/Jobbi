import { render, screen, waitFor, within } from "@testing-library/react";
import { Link, MemoryRouter, useLocation } from "react-router-dom";
import { ToastProvider } from "@/shared/ui";
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

describe("DashboardPage ?application= deep link", () => {
  function SearchProbe() {
    const location = useLocation();
    return <output aria-label="search">{location.search}</output>;
  }

  it("opens the application panel for that id and clears the param", async () => {
    localStorage.setItem("jobbi_token", "test-token");
    render(
      <MemoryRouter initialEntries={["/dashboard?application=app-1"]}>
        <ToastProvider>
          <DashboardPage />
          <SearchProbe />
        </ToastProvider>
      </MemoryRouter>,
    );

    const panel = await screen.findByRole("dialog", { name: "Application details" });
    expect(await within(panel).findByDisplayValue("Acme Corp")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("status", { name: "search" })).toBeEmptyDOMElement());
  });

  it("keeps the panel closed without the param", () => {
    renderWithProviders(<DashboardPage />);

    expect(screen.queryByRole("dialog", { name: "Application details" })).not.toBeInTheDocument();
  });

  function renderAt(entry: string) {
    localStorage.setItem("jobbi_token", "test-token");
    return render(
      <MemoryRouter initialEntries={[entry]}>
        <ToastProvider>
          <DashboardPage />
          <SearchProbe />
          <Link to="/dashboard?application=app-1">Open app-1 again</Link>
        </ToastProvider>
      </MemoryRouter>,
    );
  }

  it("opens the panel again when the same link lands after the panel was closed", async () => {
    const user = userEvent.setup();
    renderAt("/dashboard?application=app-1");
    await screen.findByRole("dialog", { name: "Application details" });
    await waitFor(() => expect(screen.getByRole("status", { name: "search" })).toBeEmptyDOMElement());

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Application details" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Open app-1 again" }));

    const panel = await screen.findByRole("dialog", { name: "Application details" });
    expect(await within(panel).findByDisplayValue("Acme Corp")).toBeInTheDocument();
  });

  it("shows Application not found for an unknown id", async () => {
    renderAt("/dashboard?application=missing");

    const panel = await screen.findByRole("dialog", { name: "Application details" });
    expect(await within(panel).findByText("Application not found")).toBeInTheDocument();
    expect(within(panel).queryByText(/Request failed/)).not.toBeInTheDocument();
  });

  it("drops an empty ?application= without opening the panel", async () => {
    renderAt("/dashboard?application=");

    await waitFor(() => expect(screen.getByRole("status", { name: "search" })).toBeEmptyDOMElement());
    expect(screen.queryByRole("dialog", { name: "Application details" })).not.toBeInTheDocument();
  });
});
