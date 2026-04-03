import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RegisterPage } from "@/pages/register/ui/register-page";
import { useAuthStore } from "@/features/auth";
import { renderWithProviders } from "./utils";

beforeEach(() => {
  localStorage.clear();
  useAuthStore.setState({ token: null, isAuthenticated: false });
});

describe("RegisterPage", () => {
  it("renders register form with all fields", () => {
    renderWithProviders(<RegisterPage />);

    expect(
      screen.getByRole("heading", { name: /create your jobbi account/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/full name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/desired role/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/desired location/i)).toBeInTheDocument();
    expect(screen.getByText(/remote preference/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /create account/i }),
    ).toBeInTheDocument();
  });

  it("shows validation for required fields", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />);

    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(screen.getByText(/full name is required/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/invalid email/i)).toBeInTheDocument();
  });

  it("shows validation for short password", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />);

    await user.type(screen.getByLabelText(/full name/i), "Test User");
    await user.type(screen.getByLabelText(/email/i), "new@example.com");
    await user.type(screen.getByLabelText(/^password/i), "short");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/password must be at least 8 characters/i),
      ).toBeInTheDocument();
    });
  });

  it("successful registration stores token and navigates", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />);

    await user.type(screen.getByLabelText(/full name/i), "New User");
    await user.type(screen.getByLabelText(/email/i), "new@example.com");
    await user.type(screen.getByLabelText(/^password/i), "securepassword123");

    // Select a valid remote preference to avoid zod enum validation
    // rejecting the empty-string default from the <select>.
    const selectElement = screen.getByRole("combobox");
    await user.selectOptions(selectElement, "remote");

    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      const state = useAuthStore.getState();
      expect(state.token).toBe("fake-register-token");
      expect(state.isAuthenticated).toBe(true);
    });
  });
});
