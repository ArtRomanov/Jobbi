import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { useAuthStore } from "@/features/auth";
import { appRoutes } from "@/app/router";

/** Renders the real app route table in a data router, starting at `path`. */
function renderAppAt(path: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
}

beforeEach(() => {
  localStorage.clear();
  useAuthStore.setState({ token: null, isAuthenticated: false });
});

describe("App routes and ProtectedRoute", () => {
  it.each(["/dashboard", "/cvs/new", "/cvs/cv-1/edit", "/applications/app-1/chat"])(
    "redirects a guest from %s to /login",
    async (path) => {
      const router = renderAppAt(path);

      expect(await screen.findByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
      expect(router.state.location.pathname).toBe("/login");
    },
  );

  it("sends an unknown URL to /dashboard, which sends a guest to /login", async () => {
    const router = renderAppAt("/no-such-page");

    expect(await screen.findByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
  });

  it("renders the app shell for an authenticated user", async () => {
    localStorage.setItem("jobbi_token", "valid-token");
    useAuthStore.setState({ token: "valid-token", isAuthenticated: true });

    const router = renderAppAt("/dashboard");

    expect(await screen.findByRole("button", { name: "Log Out" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /welcome back/i })).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/dashboard");
  });

  it("sends an authenticated user from an unknown URL to /dashboard", async () => {
    localStorage.setItem("jobbi_token", "valid-token");
    useAuthStore.setState({ token: "valid-token", isAuthenticated: true });

    const router = renderAppAt("/no-such-page");

    expect(await screen.findByRole("button", { name: "Log Out" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/dashboard");
  });
});
