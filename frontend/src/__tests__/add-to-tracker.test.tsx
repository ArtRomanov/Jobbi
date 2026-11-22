import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { http, HttpResponse, delay } from "msw";
import { InboxPage } from "@/pages/inbox";
import { ChatPage } from "@/pages/chat";
import { useNewVacancyCount } from "@/entities/vacancy";
import { ToastProvider } from "@/shared/ui";
import { mockVacancy, mockVacancyPageEmpty } from "./mocks/handlers";
import { server } from "./setup";

const VACANCIES_URL = "*/api/v1/vacancies";
const ADD_URL = "*/api/v1/vacancies/:id/add-to-tracker";
const SEEN_URL = "*/api/v1/vacancies/:id/seen";
const CVS_URL = "*/api/v1/cvs";
const CHAT_URL = "*/api/v1/applications/:id/chat";
const NEW_COUNT_URL = "*/api/v1/vacancies/new-count";

const EXISTING = { id: "app-9", company_name: "Acme Corp", role_title: "Senior Engineer" };

type MockVacancy = typeof mockVacancy & { existing_application?: typeof EXISTING | null };

function serveVacancies(items: MockVacancy[]): void {
  server.use(
    http.get(VACANCIES_URL, () =>
      HttpResponse.json({ ...mockVacancyPageEmpty, items, total: items.length }),
    ),
  );
}

type Reply = () => Response | Promise<Response>;

/** Records add-to-tracker bodies; replies come from `replies` in order (last one repeats). */
function recordAdds(...replies: Reply[]): Record<string, unknown>[] {
  const bodies: Record<string, unknown>[] = [];
  server.use(
    http.post(ADD_URL, async ({ request }) => {
      bodies.push((await request.json()) as Record<string, unknown>);
      const reply = replies[Math.min(bodies.length - 1, replies.length - 1)];
      return reply
        ? reply()
        : HttpResponse.json({ application_id: "app-1", cv_id: null }, { status: 201 });
    }),
  );
  return bodies;
}

function recordSeen(): string[] {
  const ids: string[] = [];
  server.use(
    http.post(SEEN_URL, ({ params }) => {
      ids.push(String(params.id));
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return ids;
}

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location">{`${location.pathname}${location.search}`}</output>;
}

/** Stands in for the nav badge, which refetches on `notifyVacanciesChanged()`. */
function CountProbe() {
  const count = useNewVacancyCount();
  return <output aria-label="new count">{count}</output>;
}

function renderApp() {
  return render(
    <MemoryRouter initialEntries={["/inbox"]}>
      <ToastProvider>
        <Routes>
          <Route
            path="/inbox"
            element={
              <>
                <CountProbe />
                <InboxPage />
              </>
            }
          />
          <Route path="/dashboard" element={<LocationProbe />} />
          <Route path="/applications/:id/chat" element={<ChatPage />} />
        </Routes>
      </ToastProvider>
    </MemoryRouter>,
  );
}

async function findCard(): Promise<HTMLElement> {
  const heading = await screen.findByRole("heading", { name: "Senior React Developer" });
  return heading.closest("article")!;
}

async function openDialog() {
  const user = userEvent.setup();
  renderApp();
  const card = await findCard();
  await user.click(within(card).getByRole("button", { name: /^Add to tracker: / }));
  const dialog = screen.getByRole("dialog", { name: "Add to tracker" });
  return { user, card, dialog };
}

/** The dialog's own submit button (the card has one with the same name). */
function dialogButton(dialog: HTMLElement, name: string): HTMLElement {
  return within(dialog).getByRole("button", { name });
}

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
});

describe("Add to tracker dialog", () => {
  it("prefills company, role and the full text, and defaults to the most recently updated CV", async () => {
    serveVacancies([mockVacancy]);
    const { dialog } = await openDialog();

    expect(within(dialog).getByRole("textbox", { name: "Company" })).toHaveValue("Acme");
    expect(within(dialog).getByRole("textbox", { name: "Role" })).toHaveValue("Senior React Developer");
    expect(within(dialog).getByRole("textbox", { name: "Notes" })).toHaveValue(mockVacancy.text);
    expect(within(dialog).getByRole("textbox", { name: "Company" })).toHaveFocus();
    // cv-2 was updated 2026-03-01, cv-1 on 2026-02-20
    await waitFor(() =>
      expect(within(dialog).getByRole("combobox", { name: "Base CV" })).toHaveValue("cv-2"),
    );
  });

  it("shows Required for an empty or blank company/role and sends nothing", async () => {
    serveVacancies([{ ...mockVacancy, company: null }]);
    const bodies = recordAdds();
    const { user, dialog } = await openDialog();
    const role = within(dialog).getByRole("textbox", { name: "Role" });
    await user.clear(role);
    await user.type(role, "   ");

    await user.click(dialogButton(dialog, "Add to tracker"));

    expect(await within(dialog).findAllByText("Required")).toHaveLength(2);
    expect(within(dialog).getByRole("textbox", { name: "Company" })).toHaveAttribute("aria-invalid", "true");
    expect(bodies).toEqual([]);
  });

  it("adds, removes the card, refreshes the badge and shows a toast linking to the application", async () => {
    serveVacancies([mockVacancy]);
    const bodies = recordAdds();
    let newCountCalls = 0;
    server.use(
      http.get(NEW_COUNT_URL, () => {
        newCountCalls += 1;
        return HttpResponse.json({ count: 0 });
      }),
    );
    const { user, dialog } = await openDialog();
    const company = within(dialog).getByRole("textbox", { name: "Company" });
    await user.clear(company);
    await user.type(company, "  Acme GmbH  ");
    await waitFor(() => expect(newCountCalls).toBeGreaterThan(0));
    const callsBefore = newCountCalls;

    await user.click(dialogButton(dialog, "Add to tracker"));

    const link = await screen.findByRole("link", { name: "Open application" });
    expect(bodies).toEqual([
      {
        company_name: "Acme GmbH",
        role_title: "Senior React Developer",
        notes: mockVacancy.text,
        base_cv_id: null,
        allow_duplicate: false,
      },
    ]);
    expect(screen.getByText("Added to tracker")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Senior React Developer" })).not.toBeInTheDocument();
    await waitFor(() => expect(newCountCalls).toBeGreaterThan(callsBefore));

    await user.click(link);
    expect(screen.getByRole("status", { name: "location" })).toHaveTextContent(
      "/dashboard?application=app-1",
    );
  });

  it("Add & tailor CV sends the base CV and opens the chat with an unsent draft", async () => {
    serveVacancies([mockVacancy]);
    const bodies = recordAdds(() =>
      HttpResponse.json({ application_id: "app-1", cv_id: "cv-copy" }, { status: 201 }),
    );
    let chatPosts = 0;
    server.use(
      http.post(CHAT_URL, () => {
        chatPosts += 1;
        return new HttpResponse(null, { status: 500 });
      }),
    );
    const { user, dialog } = await openDialog();
    const tailor = dialogButton(dialog, "Add & tailor CV");
    await waitFor(() => expect(tailor).toBeEnabled());
    await user.selectOptions(within(dialog).getByRole("combobox", { name: "Base CV" }), "cv-1");

    await user.click(tailor);

    const input = await screen.findByRole("textbox", { name: "Chat message" });
    expect(input).toHaveValue("Adapt my CV to this vacancy");
    expect(bodies[0]).toMatchObject({ base_cv_id: "cv-1", allow_duplicate: false });
    await screen.findByText(/Acme Corp — Senior Engineer/);
    expect(chatPosts).toBe(0);
  });

  it("disables Add & tailor CV with a hint when the user has no CVs", async () => {
    serveVacancies([mockVacancy]);
    server.use(http.get(CVS_URL, () => HttpResponse.json([])));
    const { dialog } = await openDialog();

    const hint = await within(dialog).findByText("Create a CV first");
    const tailor = dialogButton(dialog, "Add & tailor CV");
    expect(tailor).toBeDisabled();
    expect(tailor).toHaveAttribute("aria-describedby", hint.id);
    expect(within(dialog).queryByRole("combobox", { name: "Base CV" })).not.toBeInTheDocument();
    expect(dialogButton(dialog, "Add to tracker")).toBeEnabled();
  });

  describe("already tracked", () => {
    it("warns from existing_application; Open it marks the card seen and opens the application", async () => {
      serveVacancies([{ ...mockVacancy, existing_application: EXISTING }]);
      const seen = recordSeen();
      const bodies = recordAdds();
      const { user, dialog } = await openDialog();

      expect(
        within(dialog).getByText("You already track this: Acme Corp — Senior Engineer"),
      ).toBeInTheDocument();

      await user.click(dialogButton(dialog, "Open it"));

      expect(screen.getByRole("status", { name: "location" })).toHaveTextContent(
        "/dashboard?application=app-9",
      );
      await waitFor(() => expect(seen).toEqual(["vac-1"]));
      expect(bodies).toEqual([]);
    });

    it("Add anyway sends allow_duplicate", async () => {
      serveVacancies([{ ...mockVacancy, existing_application: EXISTING }]);
      const bodies = recordAdds();
      const { user, dialog } = await openDialog();

      await user.click(dialogButton(dialog, "Add anyway"));

      await screen.findByRole("link", { name: "Open application" });
      expect(bodies).toEqual([expect.objectContaining({ allow_duplicate: true, base_cv_id: null })]);
    });

    it("shows the warning from a structured 409 and Add anyway repeats the same action", async () => {
      serveVacancies([mockVacancy]);
      const bodies = recordAdds(
        () =>
          HttpResponse.json(
            { detail: { message: "You already track this", application: EXISTING } },
            { status: 409 },
          ),
        () => HttpResponse.json({ application_id: "app-1", cv_id: "cv-copy" }, { status: 201 }),
      );
      const { user, dialog } = await openDialog();
      const tailor = dialogButton(dialog, "Add & tailor CV");
      await waitFor(() => expect(tailor).toBeEnabled());

      await user.click(tailor);

      expect(
        await within(dialog).findByText("You already track this: Acme Corp — Senior Engineer"),
      ).toBeInTheDocument();
      expect(within(dialog).queryByText(/Could not add/)).not.toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Senior React Developer" })).toBeInTheDocument();

      await user.click(dialogButton(dialog, "Add anyway"));

      expect(await screen.findByRole("textbox", { name: "Chat message" })).toHaveValue(
        "Adapt my CV to this vacancy",
      );
      expect(bodies.map((body) => [body.allow_duplicate, body.base_cv_id])).toEqual([
        [false, "cv-2"],
        [true, "cv-2"],
      ]);
    });
  });

  describe("failures", () => {
    it("shows the server text for a 404 and keeps the card", async () => {
      serveVacancies([mockVacancy]);
      recordAdds(() => HttpResponse.json({ detail: "CV not found." }, { status: 404 }));
      const { user, dialog } = await openDialog();

      await user.click(dialogButton(dialog, "Add to tracker"));

      expect(await within(dialog).findByRole("alert")).toHaveTextContent("CV not found.");
      expect(screen.getByRole("heading", { name: "Senior React Developer" })).toBeInTheDocument();
    });

    it("shows the generic message for a 500", async () => {
      serveVacancies([mockVacancy]);
      recordAdds(() => HttpResponse.json({ detail: "Traceback…" }, { status: 500 }));
      const { user, dialog } = await openDialog();

      await user.click(dialogButton(dialog, "Add to tracker"));

      expect(await within(dialog).findByRole("alert")).toHaveTextContent(
        "Could not add this vacancy. Please try again.",
      );
      expect(screen.queryByRole("link", { name: "Open application" })).not.toBeInTheDocument();
    });

    it("sends one request for a double click", async () => {
      serveVacancies([mockVacancy]);
      const bodies = recordAdds(async () => {
        await delay(50);
        return HttpResponse.json({ application_id: "app-1", cv_id: null }, { status: 201 });
      });
      const { user, dialog } = await openDialog();
      const submit = dialogButton(dialog, "Add to tracker");

      await user.dblClick(submit);

      await screen.findByRole("link", { name: "Open application" });
      expect(bodies).toHaveLength(1);
    });

    it("blocks Escape while the request runs", async () => {
      serveVacancies([mockVacancy]);
      recordAdds(async () => {
        await delay(50);
        return HttpResponse.json({ detail: "boom" }, { status: 500 });
      });
      const { user, dialog } = await openDialog();

      await user.click(dialogButton(dialog, "Add to tracker"));
      await user.keyboard("{Escape}");

      expect(screen.getByRole("dialog")).toBeInTheDocument();
      await within(dialog).findByText("Could not add this vacancy. Please try again.");
    });
  });
});

describe("Add to tracker — review follow-ups", () => {
  it("opening the dialog marks a new card seen", async () => {
    serveVacancies([mockVacancy]);
    const seen = recordSeen();
    const { card } = await openDialog();

    await waitFor(() => expect(seen).toEqual(["vac-1"]));
    expect(within(card).queryByText("New")).not.toBeInTheDocument();
  });

  it("does not send seen again for a card that is already seen", async () => {
    serveVacancies([{ ...mockVacancy, state: "seen" }]);
    const seen = recordSeen();
    await openDialog();

    expect(seen).toEqual([]);
  });

  it("moves focus to the next card's Dismiss button after a successful add", async () => {
    const second: MockVacancy = { ...mockVacancy, id: "vac-2", title: "Frontend Engineer", company: "Beta" };
    serveVacancies([mockVacancy, second]);
    recordAdds();
    const { user, dialog } = await openDialog();

    await user.click(dialogButton(dialog, "Add to tracker"));

    await screen.findByRole("link", { name: "Open application" });
    const nextCard = screen.getByRole("heading", { name: "Frontend Engineer" }).closest("article")!;
    await waitFor(() => expect(within(nextCard).getByRole("button", { name: /^Dismiss / })).toHaveFocus());
  });

  it("keeps focus inside the dialog while the request runs", async () => {
    serveVacancies([mockVacancy]);
    recordAdds(async () => {
      await delay(80);
      return HttpResponse.json({ detail: "boom" }, { status: 500 });
    });
    const { user, dialog } = await openDialog();

    await user.click(dialogButton(dialog, "Add to tracker"));
    await user.tab();

    expect(dialog.contains(document.activeElement)).toBe(true);
    await within(dialog).findByText("Could not add this vacancy. Please try again.");
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("describes the dialog with the warning and requires Add anyway instead of sending a doomed request", async () => {
    serveVacancies([{ ...mockVacancy, existing_application: EXISTING }]);
    const bodies = recordAdds(() =>
      HttpResponse.json({ application_id: "app-1", cv_id: "cv-copy" }, { status: 201 }),
    );
    const { user, dialog } = await openDialog();
    const warningText = within(dialog).getByText("You already track this: Acme Corp — Senior Engineer");
    expect(dialog).toHaveAttribute("aria-describedby", warningText.id);
    const tailor = dialogButton(dialog, "Add & tailor CV");
    await waitFor(() => expect(tailor).toBeEnabled());

    await user.click(tailor);

    expect(bodies).toEqual([]);
    expect(dialogButton(dialog, "Add anyway")).toHaveFocus();

    await user.click(dialogButton(dialog, "Add anyway"));

    await screen.findByRole("textbox", { name: "Chat message" });
    expect(bodies).toEqual([expect.objectContaining({ allow_duplicate: true, base_cv_id: "cv-2" })]);
  });

  it("409 Already added closes the dialog, removes the card and says so", async () => {
    serveVacancies([mockVacancy]);
    recordAdds(() => HttpResponse.json({ detail: "Already added" }, { status: 409 }));
    const { user, dialog } = await openDialog();

    await user.click(dialogButton(dialog, "Add to tracker"));

    expect(await screen.findByText("Already in your tracker")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Senior React Developer" })).not.toBeInTheDocument();
  });

  it("shows the server text for 409 Vacancy is not in the Inbox", async () => {
    serveVacancies([mockVacancy]);
    recordAdds(() => HttpResponse.json({ detail: "Vacancy is not in the Inbox." }, { status: 409 }));
    const { user, dialog } = await openDialog();

    await user.click(dialogButton(dialog, "Add to tracker"));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Vacancy is not in the Inbox.");
  });
});
