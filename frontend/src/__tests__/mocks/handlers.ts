import { http, HttpResponse } from "msw";

const BASE_URL = "http://localhost:8000";

// ---------------------------------------------------------------------------
// CV mock data
// ---------------------------------------------------------------------------

export const mockCvs = [
  {
    id: "cv-1",
    name: "Software Engineer CV",
    personal_info: {
      full_name: "Test User",
      email: "test@example.com",
      phone: "+1234567890",
      location: "Berlin, Germany",
      linkedin_url: "https://linkedin.com/in/testuser",
    },
    summary: "Experienced software engineer.",
    work_experience: [
      {
        company: "Acme Corp",
        role: "Senior Engineer",
        start_date: "2022-01",
        end_date: "",
        is_current: true,
        description: "Building products.",
      },
    ],
    education: [
      {
        institution: "MIT",
        degree: "BSc",
        field_of_study: "Computer Science",
        start_year: "2016",
        end_year: "2020",
        description: "",
      },
    ],
    skills: "TypeScript, React",
    languages: "English (Native)",
    linked_applications_count: 1,
    created_at: "2026-01-10T08:00:00Z",
    updated_at: "2026-02-20T10:00:00Z",
  },
  {
    id: "cv-2",
    name: "Frontend Developer CV",
    personal_info: null,
    summary: null,
    work_experience: null,
    education: null,
    skills: null,
    languages: null,
    linked_applications_count: 0,
    created_at: "2026-02-15T09:00:00Z",
    updated_at: "2026-03-01T12:00:00Z",
  },
];

export const mockCvDetail = { ...mockCvs[0] };

// ---------------------------------------------------------------------------
// Application mock data
// ---------------------------------------------------------------------------

export const mockApplications = [
  {
    id: "app-1",
    company_name: "Acme Corp",
    role_title: "Senior Engineer",
    status: "researching",
    job_url: "https://acme.com/jobs/1",
    salary_min: 100000,
    salary_max: 150000,
    salary_currency: "USD",
    contact_name: "Alice HR",
    contact_email: "alice@acme.com",
    notes: "Great company culture",
    created_at: "2026-01-15T10:00:00Z",
    updated_at: "2026-02-01T12:00:00Z",
  },
  {
    id: "app-2",
    company_name: "TechStart",
    role_title: "Frontend Dev",
    status: "applied",
    job_url: null,
    salary_min: null,
    salary_max: null,
    salary_currency: null,
    contact_name: null,
    contact_email: null,
    notes: null,
    created_at: "2026-02-10T09:00:00Z",
    updated_at: "2026-02-15T14:30:00Z",
  },
];

export const mockApplicationDetail = {
  ...mockApplications[0],
  status_history: [
    {
      id: "sh-1",
      status: "researching",
      changed_at: "2026-01-15T10:00:00Z",
    },
    {
      id: "sh-2",
      status: "applied",
      changed_at: "2026-01-20T11:00:00Z",
    },
  ],
};

// ---------------------------------------------------------------------------
// User mock data
// ---------------------------------------------------------------------------

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

  // -------------------------------------------------------------------------
  // Application endpoints
  // -------------------------------------------------------------------------

  // GET /api/v1/applications — paginated list with optional search filter
  http.get(`${BASE_URL}/api/v1/applications`, ({ request }) => {
    const url = new URL(request.url);
    const search = url.searchParams.get("search")?.toLowerCase();

    const filtered = search
      ? mockApplications.filter(
          (a) =>
            a.company_name.toLowerCase().includes(search) ||
            a.role_title.toLowerCase().includes(search),
        )
      : mockApplications;

    return HttpResponse.json({
      items: filtered,
      total: filtered.length,
      page: 1,
      per_page: 200,
    });
  }),

  // POST /api/v1/applications — create a new application
  http.post(`${BASE_URL}/api/v1/applications`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    const newApp = {
      id: "app-new",
      company_name: body.company_name,
      role_title: body.role_title,
      status: body.status ?? "researching",
      job_url: body.job_url ?? null,
      salary_min: body.salary_min ?? null,
      salary_max: body.salary_max ?? null,
      salary_currency: body.salary_currency ?? null,
      contact_name: body.contact_name ?? null,
      contact_email: body.contact_email ?? null,
      notes: body.notes ?? null,
      created_at: "2026-03-01T10:00:00Z",
      updated_at: "2026-03-01T10:00:00Z",
      status_history: [
        {
          id: "sh-new",
          status: body.status ?? "researching",
          changed_at: "2026-03-01T10:00:00Z",
        },
      ],
    };
    return HttpResponse.json(newApp, { status: 201 });
  }),

  // GET /api/v1/applications/history — status history feed
  http.get(`${BASE_URL}/api/v1/applications/history`, () => {
    return HttpResponse.json({
      items: [
        {
          id: "sh-1",
          application_id: "app-1",
          company_name: "Acme Corp",
          role_title: "Senior Engineer",
          status: "researching",
          changed_at: "2026-01-15T10:00:00Z",
        },
      ],
      total: 1,
      page: 1,
      per_page: 50,
    });
  }),

  // GET /api/v1/applications/:id — single application detail
  http.get(`${BASE_URL}/api/v1/applications/:id`, ({ params }) => {
    const id = params.id as string;
    const base = mockApplications.find((a) => a.id === id);
    if (!base) {
      return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    }
    return HttpResponse.json({
      ...base,
      status_history:
        id === "app-1" ? mockApplicationDetail.status_history : [],
    });
  }),

  // PATCH /api/v1/applications/:id — update application
  http.patch(
    `${BASE_URL}/api/v1/applications/:id`,
    async ({ params, request }) => {
      const id = params.id as string;
      const body = (await request.json()) as Record<string, unknown>;
      const base = mockApplications.find((a) => a.id === id);
      if (!base) {
        return HttpResponse.json({ detail: "Not found" }, { status: 404 });
      }
      return HttpResponse.json({
        ...base,
        ...body,
        status_history:
          id === "app-1" ? mockApplicationDetail.status_history : [],
      });
    },
  ),

  // DELETE /api/v1/applications/:id
  http.delete(`${BASE_URL}/api/v1/applications/:id`, () => {
    return HttpResponse.json({ message: "Application deleted" });
  }),

  // -------------------------------------------------------------------------
  // CV endpoints
  // -------------------------------------------------------------------------

  // GET /api/v1/cvs — list all CVs
  http.get(`${BASE_URL}/api/v1/cvs`, () => {
    return HttpResponse.json(mockCvs);
  }),

  // POST /api/v1/cvs — create a new CV
  http.post(`${BASE_URL}/api/v1/cvs`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    const newCv = {
      id: "cv-new",
      name: body.name ?? "Untitled CV",
      personal_info: body.personal_info ?? null,
      summary: body.summary ?? null,
      work_experience: body.work_experience ?? null,
      education: body.education ?? null,
      skills: body.skills ?? null,
      languages: body.languages ?? null,
      linked_applications_count: 0,
      created_at: "2026-03-10T10:00:00Z",
      updated_at: "2026-03-10T10:00:00Z",
    };
    return HttpResponse.json(newCv, { status: 201 });
  }),

  // GET /api/v1/cvs/:id — single CV detail
  http.get(`${BASE_URL}/api/v1/cvs/:id`, ({ params }) => {
    const id = params.id as string;
    const cv = mockCvs.find((c) => c.id === id);
    if (!cv) {
      return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    }
    return HttpResponse.json(cv);
  }),

  // PATCH /api/v1/cvs/:id — update CV
  http.patch(`${BASE_URL}/api/v1/cvs/:id`, async ({ params, request }) => {
    const id = params.id as string;
    const body = (await request.json()) as Record<string, unknown>;
    const cv = mockCvs.find((c) => c.id === id);
    if (!cv) {
      return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    }
    return HttpResponse.json({ ...cv, ...body });
  }),

  // DELETE /api/v1/cvs/:id — delete CV
  http.delete(`${BASE_URL}/api/v1/cvs/:id`, () => {
    return HttpResponse.json({ message: "CV deleted" });
  }),

  // POST /api/v1/cvs/:id/duplicate — duplicate CV
  http.post(`${BASE_URL}/api/v1/cvs/:id/duplicate`, async ({ params, request }) => {
    const id = params.id as string;
    const body = (await request.json()) as Record<string, unknown>;
    const original = mockCvs.find((c) => c.id === id);
    if (!original) {
      return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    }
    return HttpResponse.json(
      {
        ...original,
        id: "cv-duplicated",
        name: (body.name as string) ?? `${original.name} (copy)`,
        linked_applications_count: 0,
        created_at: "2026-03-10T10:00:00Z",
        updated_at: "2026-03-10T10:00:00Z",
      },
      { status: 201 },
    );
  }),
];
