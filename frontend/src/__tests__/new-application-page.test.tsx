import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NewApplicationPage } from "@/pages/new-application/ui/new-application-page";
import { renderWithProviders } from "./utils";

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
});

describe("NewApplicationPage", () => {
  it("renders form with required fields", () => {
    renderWithProviders(<NewApplicationPage />);

    expect(screen.getByLabelText(/company name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/role title/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /create application/i }),
    ).toBeInTheDocument();
  });

  it("shows validation errors when submitting empty form", async () => {
    const user = userEvent.setup();
    renderWithProviders(<NewApplicationPage />);

    await user.click(
      screen.getByRole("button", { name: /create application/i }),
    );

    await waitFor(() => {
      expect(
        screen.getByText(/company name is required/i),
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/role title is required/i)).toBeInTheDocument();
  });

  it("submits successfully when required fields are filled", async () => {
    const user = userEvent.setup();
    renderWithProviders(<NewApplicationPage />);

    await user.type(screen.getByLabelText(/company name/i), "NewCo");
    await user.type(screen.getByLabelText(/role title/i), "Full Stack Dev");

    await user.click(
      screen.getByRole("button", { name: /create application/i }),
    );

    // After successful creation the app shows a success toast
    await waitFor(() => {
      expect(screen.getByText(/application created/i)).toBeInTheDocument();
    });
  });
});
