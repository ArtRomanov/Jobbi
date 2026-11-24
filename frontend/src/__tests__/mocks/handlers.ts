import { http, HttpResponse } from "msw";
import type { ChangeCard } from "@/entities/chat";
import type { Cv } from "@/entities/cv";

const BASE_URL = "http://localhost:8000";

// ---------------------------------------------------------------------------
// CV mock data
// ---------------------------------------------------------------------------

/** Fields every CV gets unless a fixture says otherwise: an own, non-base CV. */
const OWN_CV_FIELDS = {
  is_base: false,
  kind: "own",
  tailored_for: null,
  tailored_application_deleted: false,
} as const satisfies Pick<Cv, "is_base" | "kind" | "tailored_for" | "tailored_application_deleted">;

/**
 * Server order (spec 011): base first, then own CVs, then tailored copies,
 * each by `updated_at` desc.
 */
export const mockCvs: Cv[] = [
  {
    id: "cv-1",
    name: "Software Engineer CV",
    content:
      "# Test User\ntest@example.com · +1234567890 · Berlin, Germany\n\n## Summary\nExperienced software engineer.\n\n## Skills\nTypeScript, React",
    version: 3,
    linked_applications_count: 1,
    created_at: "2026-01-10T08:00:00Z",
    updated_at: "2026-02-20T10:00:00Z",
    ...OWN_CV_FIELDS,
    is_base: true,
  },
  {
    id: "cv-2",
    name: "Frontend Developer CV",
    content: "",
    version: 1,
    linked_applications_count: 0,
    created_at: "2026-02-15T09:00:00Z",
    updated_at: "2026-03-01T12:00:00Z",
    ...OWN_CV_FIELDS,
  },
  {
    id: "cv-3",
    name: "Software Engineer CV \u2014 Acme Corp Senior Engineer",
    content: "# Test User",
    version: 2,
    linked_applications_count: 1,
    created_at: "2026-03-05T09:00:00Z",
    updated_at: "2026-03-06T12:00:00Z",
    ...OWN_CV_FIELDS,
    kind: "tailored",
    tailored_for: { application_id: "app-1", company_name: "Acme Corp", role_title: "Senior Engineer" },
  },
];

/** Builds a CV fixture: an own, non-base CV unless `overrides` say otherwise. */
export function makeMockCv(overrides: Partial<Cv> & Pick<Cv, "id" | "name">): Cv {
  return {
    content: "",
    version: 1,
    linked_applications_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...OWN_CV_FIELDS,
    ...overrides,
  };
}

export const mockCvDetail = { ...mockCvs[0] };

/** `POST /cvs/upload` response (spec 011 slice 9): the extracted text only. */
export const mockUploadDraft = {
  name: "resume",
  content: "# Ivan Petrov\nFrontend developer",
  truncated: false,
};

// ---------------------------------------------------------------------------
// Chat mock data
// ---------------------------------------------------------------------------

export const mockChatMessages = [
  {
    id: "msg-1",
    application_id: "app-1",
    role: "user",
    content: "Help me prepare for my interview at Acme Corp.",
    created_at: "2026-03-01T10:00:00Z",
    cards: [],
  },
  {
    id: "msg-2",
    application_id: "app-1",
    role: "assistant",
    content:
      "I'd be happy to help you prepare for your interview at Acme Corp! Let's start with some common questions.",
    created_at: "2026-03-01T10:01:00Z",
    cards: [],
  },
];

// ---------------------------------------------------------------------------
// Chat change cards (spec 011 slice 7) — local contract until schema regen
// ---------------------------------------------------------------------------

export const mockChangeCards = {
  replace: {
    id: "card-replace",
    op: "replace",
    before_text: "## Summary\nExperienced software engineer.",
    after_text: "## Summary\nSenior software engineer with 8 years in React.",
    position: null,
    anchor_text: null,
    state: "pending",
    cv_id: "cv-1",
    message_id: "msg-2",
    created_at: "2026-03-01T10:01:00Z",
    decided_at: null,
  },
  insert: {
    id: "card-insert",
    op: "insert",
    before_text: "",
    after_text: "GraphQL, Node.js",
    position: "after_line",
    anchor_text: "## Skills",
    state: "pending",
    cv_id: "cv-1",
    message_id: "msg-2",
    created_at: "2026-03-01T10:01:00Z",
    decided_at: null,
  },
  remove: {
    id: "card-remove",
    op: "remove",
    before_text: "test@example.com · +1234567890 · Berlin, Germany",
    after_text: "",
    position: null,
    anchor_text: null,
    state: "pending",
    cv_id: "cv-1",
    message_id: "msg-2",
    created_at: "2026-03-01T10:01:00Z",
    decided_at: null,
  },
} as const satisfies Record<string, ChangeCard>;

// ---------------------------------------------------------------------------
// Telegram mock data
// ---------------------------------------------------------------------------

export const mockTelegramStatusNotConnected = {
  connected: false,
  telegram_username: null,
  linked_at: null,
};

export const mockTelegramStatusConnected = {
  connected: true,
  telegram_username: "jobbi_tester",
  // Backend emits UTC with a "Z" suffix (older builds sent naive UTC)
  linked_at: "2026-03-10T12:00:00Z",
};

export const mockConnectionCode = {
  code: "ABC123",
  expires_at: "2026-03-10T12:10:00Z",
};

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
// Metrics mock data
// ---------------------------------------------------------------------------

export const mockMetrics = {
  range: "30d",
  from_date: "2026-03-08",
  to_date: "2026-04-07",
  kpis: {
    total_applications: 12,
    active: 8,
    response_rate: 0.5,
    interviews: 4,
  },
  pipeline: [
    { status: "researching", count: 2 },
    { status: "applied", count: 4 },
    { status: "interview", count: 3 },
    { status: "offer", count: 1 },
    { status: "rejected", count: 2 },
    { status: "withdrawn", count: 0 },
  ],
  trend: {
    granularity: "daily",
    points: [
      { date: "2026-04-05", count: 2 },
      { date: "2026-04-06", count: 1 },
      { date: "2026-04-07", count: 3 },
    ],
  },
};

// ---------------------------------------------------------------------------
// User mock data
// ---------------------------------------------------------------------------

export const mockUser = {
  id: "user-1",
  email: "test@example.com",
  full_name: "Test User",
  desired_role: null,
  desired_location: null,
  remote_preference: null,
  salary_min: null,
  salary_max: null,
  salary_currency: null,
  timezone: "Europe/Berlin",
  summary_time: "10:00",
  // Naive, like the backend: users.created_at is TIMESTAMP WITHOUT TIME ZONE
  created_at: "2026-01-01T00:00:00",
};

// ---------------------------------------------------------------------------
// Vacancy source mock data
// ---------------------------------------------------------------------------

export const mockVacancySource = {
  id: "src-1",
  key: "telegram:frontend_jobs",
  kind: "telegram" as const,
  display_name: "@frontend_jobs",
  last_checked_at: null,
  scanning: false,
  unavailable: false,
  last_error: null as string | null,
  url: null as string | null,
  job_link_contains: null as string | null,
  watching_since: null as string | null,
  name_is_custom: false,
  editable: true,
};

/** A saved web page source (watching, not checked since). */
export const mockWebSource = {
  ...mockVacancySource,
  id: "src-web",
  key: "web:src-web",
  kind: "web" as const,
  display_name: "geekjob.ru",
  url: "https://geekjob.ru/vacancies?q=react",
  last_checked_at: "2026-03-10T10:00:00Z" as string | null,
  watching_since: "2026-03-10T10:00:00Z" as string | null,
};

/** Preview of a web page: 7 found, the first 5 titles in site order. */
export const mockWebPreview = {
  kind: "web" as const,
  default_name: "geekjob.ru",
  found_count: 7,
  titles: [
    "Senior React Developer",
    "Frontend Engineer",
    "Vue Developer",
    "Fullstack JS",
    "Team Lead Frontend",
  ],
  ats_hint: null,
};

/** Board hosts the mock treats as non-web kinds (no preview UI). */
const BOARD_HOSTS = /(greenhouse\.io|lever\.co|teamtailor\.com|ashbyhq\.com)/i;

/** Mock preview kind for an input: `@name` / t.me → telegram, a board → greenhouse, other http(s) → web. */
function mockPreviewKind(input: string): "telegram" | "greenhouse" | "web" {
  const value = input.trim();
  if (/^(https?:\/\/)?t\.me\//i.test(value) || value.startsWith("@")) return "telegram";
  if (BOARD_HOSTS.test(value)) return "greenhouse";
  return /^https?:\/\//i.test(value) ? "web" : "telegram";
}

export const mockVacancySourcesEmpty = {
  sources: [],
  removed_sources: [] as Array<{ key: string; label: string }>,
  settings: { description: null },
  status: { ai_unavailable: false, limit_reached: false, waiting_count: 0 },
};

// ---------------------------------------------------------------------------
// Vacancy (Inbox card) mock data
// ---------------------------------------------------------------------------

export const mockVacancy = {
  id: "vac-1",
  title: "Senior React Developer" as string | null,
  company: "Acme" as string | null,
  url: "https://t.me/frontend_jobs/101",
  job_link: null as string | null,
  text: "Senior React Developer, fully remote, €5000–6000.",
  posted_at: "2026-11-20T10:00:00Z",
  found_at: "2026-11-20T10:05:00Z",
  state: "new" as "new" | "seen",
  fit: "high" as "high" | "medium" | "low" | null,
  fit_reason: "Remote React role with a matching salary" as string | null,
  sources: [{ key: "telegram:frontend_jobs", label: "@frontend_jobs" }],
};

export const mockVacancyPageEmpty = { items: [], total: 0, page: 1, per_page: 20 };

export const handlers = [
  // POST /api/v1/auth/register — success
  http.post(`${BASE_URL}/api/v1/auth/register`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    if (body.email === "existing@example.com") {
      return HttpResponse.json(
        { detail: "Email already registered." },
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
      { detail: "Invalid email or password." },
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
      content: body.content ?? "",
      version: 1,
      linked_applications_count: 0,
      created_at: "2026-03-10T10:00:00Z",
      updated_at: "2026-03-10T10:00:00Z",
      ...OWN_CV_FIELDS,
      // `is_base: true` makes the new CV the base (spec 011 slice 9)
      is_base: body.is_base === true,
    };
    return HttpResponse.json(newCv, { status: 201 });
  }),

  // POST /api/v1/cvs/upload — extract only: returns the draft, creates nothing
  http.post(`${BASE_URL}/api/v1/cvs/upload`, () => {
    return HttpResponse.json(mockUploadDraft);
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
    // The real API requires the loaded version and bumps it on every save
    const { version, ...changes } = body;
    if (typeof version !== "number") {
      return HttpResponse.json({ detail: "version is required" }, { status: 422 });
    }
    // `is_base` (optional) sets or clears the base with the save; omitted = unchanged
    return HttpResponse.json({ ...cv, ...changes, version: version + 1 });
  }),

  // POST /api/v1/cvs/:id/make-base — the CV becomes the base (a tailored copy becomes own)
  http.post(`${BASE_URL}/api/v1/cvs/:id/make-base`, ({ params }) => {
    const cv = mockCvs.find((c) => c.id === params.id);
    if (!cv) {
      return HttpResponse.json({ detail: "CV not found." }, { status: 404 });
    }
    return HttpResponse.json({ ...cv, is_base: true, kind: "own" });
  }),

  // DELETE /api/v1/cvs/:id — delete CV
  http.delete(`${BASE_URL}/api/v1/cvs/:id`, () => {
    return HttpResponse.json({ message: "CV deleted" });
  }),

  // -------------------------------------------------------------------------
  // Chat endpoints
  // -------------------------------------------------------------------------

  // GET /api/v1/applications/:id/chat — chat message history
  http.get(`${BASE_URL}/api/v1/applications/:id/chat`, () => {
    return HttpResponse.json(mockChatMessages);
  }),

  // POST /api/v1/applications/:id/chat/cards/:cardId/accept — apply a change card
  http.post(
    `${BASE_URL}/api/v1/applications/:id/chat/cards/:cardId/accept`,
    ({ params }) => {
      const base =
        Object.values(mockChangeCards).find((c) => c.id === params.cardId) ??
        mockChangeCards.replace;
      return HttpResponse.json({
        ...base,
        state: "accepted",
        decided_at: "2026-03-01T10:05:00Z",
      });
    },
  ),

  // POST /api/v1/applications/:id/chat/cards/:cardId/reject — reject a change card
  http.post(
    `${BASE_URL}/api/v1/applications/:id/chat/cards/:cardId/reject`,
    ({ params }) => {
      const base =
        Object.values(mockChangeCards).find((c) => c.id === params.cardId) ??
        mockChangeCards.replace;
      return HttpResponse.json({
        ...base,
        state: "rejected",
        decided_at: "2026-03-01T10:05:00Z",
      });
    },
  ),

  // DELETE /api/v1/applications/:id/chat — clear chat history
  http.delete(`${BASE_URL}/api/v1/applications/:id/chat`, () => {
    return HttpResponse.json({ message: "Chat history cleared" });
  }),

  // -------------------------------------------------------------------------
  // Telegram endpoints
  // -------------------------------------------------------------------------

  // GET /api/v1/telegram/status — link status
  http.get(`${BASE_URL}/api/v1/telegram/status`, () => {
    return HttpResponse.json(mockTelegramStatusNotConnected);
  }),

  // POST /api/v1/telegram/connection-code — one-time linking code
  http.post(`${BASE_URL}/api/v1/telegram/connection-code`, () => {
    return HttpResponse.json(mockConnectionCode, { status: 201 });
  }),

  // DELETE /api/v1/telegram/link — unlink Telegram
  http.delete(`${BASE_URL}/api/v1/telegram/link`, () => {
    return HttpResponse.json({ message: "Disconnected." });
  }),

  // -------------------------------------------------------------------------
  // Metrics endpoints
  // -------------------------------------------------------------------------

  http.get(`${BASE_URL}/api/v1/metrics`, () => {
    return HttpResponse.json(mockMetrics);
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
        // A duplicate is always an own, non-base CV
        ...OWN_CV_FIELDS,
        version: 1,
        linked_applications_count: 0,
        created_at: "2026-03-10T10:00:00Z",
        updated_at: "2026-03-10T10:00:00Z",
      },
      { status: 201 },
    );
  }),

  // -------------------------------------------------------------------------
  // Vacancy source endpoints
  // -------------------------------------------------------------------------

  http.get(`${BASE_URL}/api/v1/vacancy-sources`, () => {
    return HttpResponse.json(mockVacancySourcesEmpty);
  }),

  // Non-web kinds answer `{kind}` only; any other http(s) link is a web page
  http.post(`${BASE_URL}/api/v1/vacancy-sources/preview`, async ({ request }) => {
    const body = (await request.json()) as { input: string };
    const kind = mockPreviewKind(body.input);
    return HttpResponse.json(kind === "web" ? mockWebPreview : { kind });
  }),

  // Web links become a web source (watching since now); anything else is echoed
  // as a new Telegram source (no validation)
  http.post(`${BASE_URL}/api/v1/vacancy-sources`, async ({ request }) => {
    const body = (await request.json()) as {
      input: string;
      job_link_contains?: string | null;
      name?: string | null;
    };
    if (mockPreviewKind(body.input) === "web") {
      const now = new Date().toISOString();
      return HttpResponse.json(
        {
          ...mockWebSource,
          id: "src-web-new",
          display_name: body.name ?? mockWebPreview.default_name,
          url: body.input.trim(),
          job_link_contains: body.job_link_contains ?? null,
          last_checked_at: now,
          watching_since: now,
        },
        { status: 201 },
      );
    }
    const name = body.input.trim().replace(/^(https?:\/\/)?t\.me\/(s\/)?/, "").replace(/^@/, "");
    return HttpResponse.json(
      {
        ...mockVacancySource,
        id: `src-${name}`,
        key: `telegram:${name.toLowerCase()}`,
        display_name: `@${name}`,
        scanning: true,
      },
      { status: 201 },
    );
  }),

  http.delete(`${BASE_URL}/api/v1/vacancy-sources/:id`, () => {
    return new HttpResponse(null, { status: 204 });
  }),

  // Rename: a trimmed name becomes custom; null / "" puts the default back
  // (the mock's default is "@<id>"; no 404 or length checks). With `input`: a
  // web link keeps the id (url + pattern updated); any other link REPLACES the
  // source — a new Telegram source with id "src-<handle>", scanning
  http.patch(`${BASE_URL}/api/v1/vacancy-sources/:id`, async ({ params, request }) => {
    const body = (await request.json()) as {
      name?: string | null;
      input?: string | null;
      job_link_contains?: string | null;
    };
    const name = body.name?.trim() || null;
    const id = String(params.id);
    if (body.input && mockPreviewKind(body.input) === "web") {
      return HttpResponse.json({
        ...mockWebSource,
        id,
        key: `web:${id}`,
        url: body.input.trim(),
        job_link_contains: body.job_link_contains ?? null,
        display_name: name ?? mockWebPreview.default_name,
        name_is_custom: name !== null,
      });
    }
    if (body.input) {
      const handle = body.input.trim().replace(/^(https?:\/\/)?t\.me\/(s\/)?/, "").replace(/^@/, "");
      return HttpResponse.json({
        ...mockVacancySource,
        id: `src-${handle}`,
        key: `telegram:${handle.toLowerCase()}`,
        display_name: name ?? `@${handle}`,
        name_is_custom: name !== null,
        scanning: true,
        editable: false,
      });
    }
    return HttpResponse.json({
      ...mockVacancySource,
      id,
      display_name: name ?? `@${id}`,
      name_is_custom: name !== null,
    });
  }),

  // Echoes the update normalized like the backend: trimmed, empty description →
  // null (no limit checks).
  http.patch(`${BASE_URL}/api/v1/vacancy-search-settings`, async ({ request }) => {
    const body = (await request.json()) as { description?: string | null };
    const description = body.description?.trim() || null;
    return HttpResponse.json({ description });
  }),

  // -------------------------------------------------------------------------
  // Vacancy (Inbox) endpoints
  // -------------------------------------------------------------------------

  http.get(`${BASE_URL}/api/v1/vacancies`, () => {
    return HttpResponse.json(mockVacancyPageEmpty);
  }),

  http.get(`${BASE_URL}/api/v1/vacancies/new-count`, () => {
    return HttpResponse.json({ count: 0 });
  }),

  // State changes: new → seen, new|seen → dismissed, dismissed → seen
  http.post(`${BASE_URL}/api/v1/vacancies/:id/seen`, () => new HttpResponse(null, { status: 204 })),
  http.post(`${BASE_URL}/api/v1/vacancies/:id/dismiss`, () => new HttpResponse(null, { status: 204 })),
  http.post(`${BASE_URL}/api/v1/vacancies/:id/restore`, () => new HttpResponse(null, { status: 204 })),
];
