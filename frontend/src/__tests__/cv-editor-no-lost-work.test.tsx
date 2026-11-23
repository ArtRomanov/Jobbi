import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { InitialEntry } from "react-router-dom";
import { CvEditorPage } from "@/pages/cv-editor";
import { mockCvs } from "./mocks/handlers";
import { server } from "./setup";
import { renderWithProviders } from "./utils";

vi.mock("@/features/cv-pdf", () => ({ downloadCvTextPdf: vi.fn().mockResolvedValue(undefined) }));

const CVS_URL = "*/api/v1/cvs";
const CV_URL = "*/api/v1/cvs/:id";
const SAVE_FAILED = "Could not save the CV. Please try again.";
const CHANGED_ELSEWHERE =
  "This CV was changed elsewhere (for example in the AI chat). Reload to see the latest version.";
const LEAVE_PROMPT = "You have unsaved changes. Leave without saving?";

const savedCv = mockCvs[0]!;

function renderEditor(url: string, initialEntries: InitialEntry[] = [url]) {
  return renderWithProviders(<CvEditorPage />, {
    initialEntries,
    path: "/cvs/new",
    routes: [
      { path: "/cvs/:id/edit", element: <CvEditorPage /> },
      { path: "/cvs", element: <p>CVs list</p> },
    ],
  });
}

async function renderLoadedEditor(initialEntries?: InitialEntry[]) {
  const result = renderEditor("/cvs/cv-1/edit", initialEntries);
  await screen.findByDisplayValue(savedCv.name);
  return result;
}

function textArea(): HTMLTextAreaElement {
  return screen.getByRole("textbox", { name: "CV text" }) as HTMLTextAreaElement;
}

function nameInput(): HTMLInputElement {
  return screen.getByRole("textbox", { name: /cv name/i }) as HTMLInputElement;
}

function saveButton(): HTMLButtonElement {
  return screen.getByRole("button", { name: "Save" }) as HTMLButtonElement;
}

/** True when a `beforeunload` listener asked the browser to prompt. */
function firesLeavePrompt(): boolean {
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  return event.defaultPrevented;
}

function echoPatch() {
  return http.patch(CV_URL, async ({ request }) => {
    const body = (await request.json()) as { version: number };
    return HttpResponse.json({ ...savedCv, ...body, version: body.version + 1 });
  });
}

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
});

describe("Save is active only with changes", () => {
  it("is disabled until the text changes and again after reverting it", async () => {
    const user = userEvent.setup();
    await renderLoadedEditor();

    expect(saveButton()).toBeDisabled();
    await user.type(textArea(), "!");
    expect(saveButton()).toBeEnabled();
    await user.type(textArea(), "{Backspace}");
    expect(saveButton()).toBeDisabled();
  });

  it("is disabled until the name changes and again after reverting it", async () => {
    const user = userEvent.setup();
    await renderLoadedEditor();

    await user.type(nameInput(), "X");
    expect(saveButton()).toBeEnabled();
    await user.type(nameInput(), "{Backspace}");
    expect(saveButton()).toBeDisabled();
    // Spaces around the name are trimmed on save, so they are no change
    await user.type(nameInput(), "  ");
    expect(saveButton()).toBeDisabled();
  });

  it("is disabled on a new empty CV", () => {
    renderEditor("/cvs/new");

    expect(saveButton()).toBeDisabled();
  });

  it("is disabled again after a successful save, until the next change", async () => {
    const user = userEvent.setup();
    server.use(echoPatch());
    await renderLoadedEditor();

    await user.type(textArea(), "\nGo");
    await user.click(saveButton());
    expect(await screen.findByText("CV saved")).toBeInTheDocument();

    expect(saveButton()).toBeDisabled();
    await user.type(textArea(), "!");
    expect(saveButton()).toBeEnabled();
  });
});

describe("Name and text limits", () => {
  it("shows Required while the name is only spaces, and sends nothing", async () => {
    const user = userEvent.setup();
    let patches = 0;
    server.use(
      http.patch(CV_URL, () => {
        patches += 1;
        return HttpResponse.json(savedCv);
      }),
    );
    await renderLoadedEditor();

    await user.clear(nameInput());
    await user.type(nameInput(), "   ");

    expect(screen.getByRole("alert")).toHaveTextContent("Required");
    await user.click(saveButton());
    expect(patches).toBe(0);
  });

  it("shows the N / 20 000 counter only above 18 000 characters", () => {
    renderEditor("/cvs/new");

    fireEvent.change(textArea(), { target: { value: "a".repeat(18_000) } });
    expect(screen.queryByText(/\/ 20 000/)).not.toBeInTheDocument();

    fireEvent.change(textArea(), { target: { value: "a".repeat(18_001) } });
    expect(screen.getByText("18 001 / 20 000")).toBeInTheDocument();
    expect(textArea()).toHaveAccessibleDescription(expect.stringContaining("18 001 / 20 000"));

    fireEvent.change(textArea(), { target: { value: "a".repeat(20_000) } });
    expect(screen.getByText("20 000 / 20 000")).toBeInTheDocument();
  });
});

describe("Save failures keep the draft", () => {
  it.each([500, 422, 404])("shows the save error for a %i and keeps the text", async (status) => {
    const user = userEvent.setup();
    server.use(http.patch(CV_URL, () => HttpResponse.json({ detail: "Boom" }, { status })));
    await renderLoadedEditor();

    await user.type(textArea(), "\nUnsaved");
    await user.click(saveButton());

    expect(await screen.findByRole("alert")).toHaveTextContent(SAVE_FAILED);
    expect(screen.getByRole("alert").textContent).toBe(SAVE_FAILED);
    expect(textArea()).toHaveValue(`${savedCv.content}\nUnsaved`);
    expect(saveButton()).toBeEnabled();
  });

  it("shows the save error when creating a CV fails", async () => {
    const user = userEvent.setup();
    server.use(http.post(CVS_URL, () => HttpResponse.error()));
    const { router } = renderEditor("/cvs/new");

    await user.type(nameInput(), "New");
    await user.type(textArea(), "# Me");
    await user.click(saveButton());

    expect(await screen.findByRole("alert")).toHaveTextContent(SAVE_FAILED);
    expect(textArea()).toHaveValue("# Me");
    expect(router.state.location.pathname).toBe("/cvs/new");
  });

  it("shows the changed-elsewhere message on 409 CV_CHANGED and does not overwrite the draft", async () => {
    const user = userEvent.setup();
    let patches = 0;
    server.use(
      http.patch(CV_URL, () => {
        patches += 1;
        return HttpResponse.json({ detail: "CV_CHANGED" }, { status: 409 });
      }),
    );
    await renderLoadedEditor();

    await user.clear(nameInput());
    await user.type(nameInput(), "Mine");
    await user.type(textArea(), "\nMy edit");
    await user.click(saveButton());

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(CHANGED_ELSEWHERE);
    expect(screen.queryByText("CV saved")).not.toBeInTheDocument();
    expect(nameInput()).toHaveValue("Mine");
    expect(textArea()).toHaveValue(`${savedCv.content}\nMy edit`);
    expect(patches).toBe(1);
    // Still unsaved: Save stays active and leaving is still guarded
    expect(saveButton()).toBeEnabled();
    expect(firesLeavePrompt()).toBe(true);
  });

  it("treats a 409 with another code as an ordinary save failure", async () => {
    const user = userEvent.setup();
    server.use(
      http.patch(CV_URL, () => HttpResponse.json({ detail: "Something else" }, { status: 409 })),
    );
    await renderLoadedEditor();

    await user.type(textArea(), "!");
    await user.click(saveButton());

    expect((await screen.findByRole("alert")).textContent).toBe(SAVE_FAILED);
  });

  it("clears the error once a later save succeeds", async () => {
    const user = userEvent.setup();
    server.use(
      http.patch(CV_URL, () => HttpResponse.json({ detail: "Boom" }, { status: 500 }), {
        once: true,
      }),
      echoPatch(),
    );
    await renderLoadedEditor();

    await user.type(textArea(), "!");
    await user.click(saveButton());
    expect(await screen.findByText(SAVE_FAILED)).toBeInTheDocument();

    await user.click(saveButton());
    expect(await screen.findByText("CV saved")).toBeInTheDocument();
    expect(screen.queryByText(SAVE_FAILED)).not.toBeInTheDocument();
  });
});

describe("Leaving with unsaved changes", () => {
  it("asks before following a link; Stay keeps the draft, Leave goes", async () => {
    const user = userEvent.setup();
    const { router } = await renderLoadedEditor();

    await user.type(textArea(), "\nDraft");
    await user.click(screen.getByRole("link", { name: /back to cvs/i }));

    const dialog = await screen.findByRole("dialog", { name: "Unsaved changes" });
    expect(dialog).toHaveAccessibleDescription(LEAVE_PROMPT);
    await user.click(within(dialog).getByRole("button", { name: "Stay" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(router.state.location.pathname).toBe("/cvs/cv-1/edit");
    expect(textArea()).toHaveValue(`${savedCv.content}\nDraft`);

    await user.click(screen.getByRole("link", { name: /back to cvs/i }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Leave" }),
    );

    expect(await screen.findByText("CVs list")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/cvs");
  });

  it("focuses Stay first, so Enter keeps the draft", async () => {
    const user = userEvent.setup();
    const { router } = await renderLoadedEditor();

    await user.type(textArea(), "\nDraft");
    await user.click(screen.getByRole("link", { name: /back to cvs/i }));
    const dialog = await screen.findByRole("dialog", { name: "Unsaved changes" });

    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Stay" })).toHaveFocus());
    await user.keyboard("{Enter}");

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(router.state.location.pathname).toBe("/cvs/cv-1/edit");
    expect(textArea()).toHaveValue(`${savedCv.content}\nDraft`);
  });

  it("treats Escape as Stay", async () => {
    const user = userEvent.setup();
    const { router } = await renderLoadedEditor();

    await user.type(textArea(), "\nDraft");
    await user.click(screen.getByRole("link", { name: /back to cvs/i }));
    await screen.findByRole("dialog", { name: "Unsaved changes" });

    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(router.state.location.pathname).toBe("/cvs/cv-1/edit");
    expect(screen.queryByText("CVs list")).not.toBeInTheDocument();
    expect(textArea()).toHaveValue(`${savedCv.content}\nDraft`);
    // Still guarded afterwards
    await user.click(screen.getByRole("link", { name: /back to cvs/i }));
    expect(await screen.findByRole("dialog", { name: "Unsaved changes" })).toBeInTheDocument();
  });

  it("asks on the browser's Back button too", async () => {
    const user = userEvent.setup();
    const { router } = await renderLoadedEditor(["/cvs", "/cvs/cv-1/edit"]);

    await user.type(textArea(), "!");
    await act(async () => {
      await router.navigate(-1);
    });

    expect(await screen.findByRole("dialog", { name: "Unsaved changes" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/cvs/cv-1/edit");
  });

  it("does not ask without changes, or after the changes were saved", async () => {
    const user = userEvent.setup();
    server.use(echoPatch());
    const { router } = await renderLoadedEditor();

    await user.type(textArea(), "!");
    await user.click(saveButton());
    expect(await screen.findByText("CV saved")).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: /back to cvs/i }));

    expect(await screen.findByText("CVs list")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/cvs");
  });

  it("does not ask when the first save moves /cvs/new to the CV's edit URL", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(CVS_URL, async ({ request }) => {
        const body = (await request.json()) as { name: string; content: string };
        return HttpResponse.json({ ...savedCv, ...body, id: "cv-new", version: 1 }, { status: 201 });
      }),
    );
    const { router } = renderEditor("/cvs/new");

    await user.type(nameInput(), "New");
    await user.type(textArea(), "# Me");
    await user.click(saveButton());

    await waitFor(() => expect(router.state.location.pathname).toBe("/cvs/cv-new/edit"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
  });

  it("does not ask when the upload notice clears its router state (same-URL replace)", async () => {
    const user = userEvent.setup();
    const { router } = await renderLoadedEditor([
      { pathname: "/cvs/cv-1/edit", state: { uploadNotice: { truncated: false, becameBase: false } } },
    ]);

    expect(screen.getByRole("status")).toHaveTextContent("Text extracted from your file.");
    await waitFor(() => expect(router.state.location.state).toBeNull());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    // A dirty draft cannot exist at mount, so replay the notice's replace while dirty
    await user.type(textArea(), "!");
    await act(async () => {
      await router.navigate(
        { pathname: "/cvs/cv-1/edit" },
        { replace: true, state: { uploadNotice: { truncated: false, becameBase: false } } },
      );
    });
    await waitFor(() => expect(router.state.location.state).toBeNull());

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/cvs/cv-1/edit");
    expect(textArea()).toHaveValue(`${savedCv.content}!`);
    expect(screen.getByRole("status")).toHaveTextContent("Text extracted from your file.");
  });

  it("asks the browser to prompt on close or reload only while there are changes", async () => {
    const user = userEvent.setup();
    server.use(echoPatch());
    await renderLoadedEditor();

    expect(firesLeavePrompt()).toBe(false);
    await user.type(textArea(), "!");
    expect(firesLeavePrompt()).toBe(true);
    await user.type(textArea(), "{Backspace}");
    expect(firesLeavePrompt()).toBe(false);

    await user.type(textArea(), "?");
    await user.click(saveButton());
    expect(await screen.findByText("CV saved")).toBeInTheDocument();
    expect(firesLeavePrompt()).toBe(false);
  });
});
