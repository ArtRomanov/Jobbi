import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LoginPage } from "@/pages/login/ui/login-page";
import { useAuthStore } from "@/features/auth";
import { renderWithProviders } from "./utils";

beforeEach(() => {
  localStorage.clear();
  useAuthStore.setState({ token: null, isAuthenticated: false });
});

describe("LoginPage", () => {
  it("renders login form", () => {
    renderWithProviders(<LoginPage />);

    expect(
      screen.getByRole("heading", { name: /welcome back/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /sign in/i }),
    ).toBeInTheDocument();
  });

  it("shows validation errors for empty fields", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />);

    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText(/invalid email/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/password is required/i)).toBeInTheDocument();
  });

  it("successful login stores token", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />);

    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.type(screen.getByLabelText(/password/i), "correct123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      const state = useAuthStore.getState();
      expect(state.token).toBe("fake-login-token");
      expect(state.isAuthenticated).toBe(true);
    });
  });

  it("wrong credentials shows error", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />);

    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.type(screen.getByLabelText(/password/i), "wrongpassword");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/invalid email or password/i),
      ).toBeInTheDocument();
    });
  });
});
