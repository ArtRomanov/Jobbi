import { http, HttpResponse } from "msw";

const BASE_URL = "http://localhost:8000";

const mockUser = {
  id: "user-1",
  email: "test@example.com",
  full_name: "Test User",
  desired_role: null,
  desired_location: null,
  remote_preference: null,
  salary_min: null,
  salary_max: null,
  salary_currency: null,
  created_at: "2026-01-01T00:00:00Z",
};

export const handlers = [
  // POST /api/v1/auth/register — success
  http.post(`${BASE_URL}/api/v1/auth/register`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    if (body.email === "existing@example.com") {
      return HttpResponse.json(
        { detail: "Email already registered" },
        { status: 409 },
      );
    }
    return HttpResponse.json({
      access_token: "fake-register-token",
      token_type: "bearer",
      user: {
        id: "user-2",
        email: body.email,
        full_name: body.full_name,
      },
    });
  }),

  // POST /api/v1/auth/login — success or 401
  http.post(`${BASE_URL}/api/v1/auth/login`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    if (body.email === "test@example.com" && body.password === "correct123") {
      return HttpResponse.json({
        access_token: "fake-login-token",
        token_type: "bearer",
        user: {
          id: "user-1",
          email: "test@example.com",
          full_name: "Test User",
        },
      });
    }
    return HttpResponse.json(
      { detail: "Invalid credentials" },
      { status: 401 },
    );
  }),

  // GET /api/v1/users/me
  http.get(`${BASE_URL}/api/v1/users/me`, () => {
    return HttpResponse.json(mockUser);
  }),

  // PATCH /api/v1/users/me
  http.patch(`${BASE_URL}/api/v1/users/me`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({ ...mockUser, ...body });
  }),

  // POST /api/v1/users/me/change-password
  http.post(
    `${BASE_URL}/api/v1/users/me/change-password`,
    async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      if (body.current_password === "wrong-password") {
        return HttpResponse.json(
          { detail: "Current password is incorrect" },
          { status: 400 },
        );
      }
      return HttpResponse.json({ message: "Password changed" });
    },
  ),

  // POST /api/v1/auth/forgot-password
  http.post(`${BASE_URL}/api/v1/auth/forgot-password`, () => {
    return HttpResponse.json({ message: "Reset email sent" });
  }),

  // POST /api/v1/auth/reset-password
  http.post(`${BASE_URL}/api/v1/auth/reset-password`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    if (body.token === "expired-token") {
      return HttpResponse.json(
        { detail: "Token has expired" },
        { status: 400 },
      );
    }
    return HttpResponse.json({ message: "Password reset successful" });
  }),

  // POST /api/v1/auth/logout
  http.post(`${BASE_URL}/api/v1/auth/logout`, () => {
    return HttpResponse.json({ message: "Logged out" });
  }),
];
