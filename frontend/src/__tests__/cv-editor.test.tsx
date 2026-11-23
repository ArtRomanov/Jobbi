import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { CvEditorPage } from "@/pages/cv-editor";
import { downloadCvTextPdf } from "@/features/cv-pdf";
import { CV_CONTENT_MAX_LENGTH } from "@/features/cv-text-editor";
import { insertTextWithinLimit } from "@/features/cv-text-editor/lib/insert-text-within-limit";
import { mockCvs } from "./mocks/handlers";
import { server } from "./setup";
import { renderWithProviders } from "./utils";

vi.mock("@/features/cv-pdf", () => ({ downloadCvTextPdf: vi.fn().mockResolvedValue(undefined) }));

const CVS_URL = "*/api/v1/cvs";
const CV_URL = "*/api/v1/cvs/:id";
const PLACEHOLDER = "Write your CV here, or upload a PDF/DOCX on the CVs page.";
const HINT = "# Heading · ## Section · **bold** · - list · [link](https://…)";
const HINT_DESCRIPTION =
  "Formatting: start a line with # for a heading, ## for a section, wrap text in two asterisks for bold, start a line with a dash for a list item, write links as text in square brackets followed by the address in parentheses.";
const PHONE_QUERY = "(max-width: 640px)";

function renderEditor(url: string) {
  // The same two routes as the real router, so create → edit is a real navigation
  return renderWithProviders(<CvEditorPage />, {
    initialEntries: [url],
    path: "/cvs/new",
    routes: [{ path: "/cvs/:id/edit", element: <CvEditorPage /> }],
  });
}

function textArea(): HTMLTextAreaElement {
  return screen.getByRole("textbox", { name: "CV text" }) as HTMLTextAreaElement;
}

function nameInput(): HTMLInputElement {
  return screen.getByRole("textbox", { name: /cv name/i }) as HTMLInputElement;
}

function mockPhoneWidth(isPhone: boolean): void {
  vi.spyOn(window, "matchMedia").mockImplementation((query: string) => ({
    matches: isPhone && query === PHONE_QUERY,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.mocked(downloadCvTextPdf).mockClear();
});

describe("CvEditorPage — create", () => {
  it("opens with an empty name, an empty text with the placeholder and the formatting hint", () => {
    renderEditor("/cvs/new");

    expect(screen.getByRole("heading", { name: "Create New CV" })).toBeInTheDocument();
    expect(nameInput()).toHaveValue("");
    expect(nameInput()).toHaveAttribute("maxLength", "255");
    expect(textArea()).toHaveValue("");
    expect(textArea()).toHaveAttribute("placeholder", PLACEHOLDER);
    expect(textArea()).toHaveAttribute("maxLength", String(CV_CONTENT_MAX_LENGTH));
    // The symbols stay on screen but are hidden from screen readers, which
    // read the plain-words description instead
    expect(screen.getByText(HINT)).toBeVisible();
    expect(screen.getByText(HINT)).toHaveAttribute("aria-hidden", "true");
    expect(textArea()).toHaveAccessibleDescription(HINT_DESCRIPTION);
    expect(screen.queryByRole("button", { name: "Export PDF" })).not.toBeInTheDocument();
  });

  it("updates the preview as the user types", async () => {
    const user = userEvent.setup();
    renderEditor("/cvs/new");
    const preview = screen.getByRole("region", { name: "Preview" });

    await user.type(textArea(), "# Jane Doe\n- React");

    await waitFor(() => {
      expect(within(preview).getByRole("heading", { name: "Jane Doe" })).toBeInTheDocument();
    });
    expect(within(preview).getByRole("listitem")).toHaveTextContent("React");
  });

  it.each([
    ["empty", ""],
    ["only spaces", "   "],
  ])("shows Required and sends nothing for a name that is %s", async (_label, name) => {
    const user = userEvent.setup();
    const posts: unknown[] = [];
    server.use(
      http.post(CVS_URL, async ({ request }) => {
        posts.push(await request.json());
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    renderEditor("/cvs/new");

    // Some text, so the draft differs from the (empty) saved version and Save is active
    await user.type(textArea(), "# Me");
    if (name) await user.type(nameInput(), name);
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Required");
    expect(nameInput()).toHaveAttribute("aria-invalid", "true");
    expect(posts).toEqual([]);

    await user.type(nameInput(), "CV");
    expect(screen.queryByText("Required")).not.toBeInTheDocument();
  });

  it("creates the CV with the trimmed name and the text, then edits it without reloading", async () => {
    const user = userEvent.setup();
    const posts: unknown[] = [];
    let gets = 0;
    server.use(
      http.post(CVS_URL, async ({ request }) => {
        const body = (await request.json()) as { name: string; content: string };
        posts.push(body);
        return HttpResponse.json(
          { ...mockCvs[1]!, id: "cv-new", name: body.name, content: body.content, version: 1 },
          { status: 201 },
        );
      }),
      http.get(CV_URL, () => {
        gets += 1;
        return HttpResponse.json(mockCvs[0]);
      }),
    );
    const { router } = renderEditor("/cvs/new");

    await user.type(nameInput(), "  My CV  ");
    await user.type(textArea(), "# Me");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("CV saved")).toBeInTheDocument();
    expect(posts).toEqual([{ name: "My CV", content: "# Me" }]);
    await waitFor(() => expect(router.state.location.pathname).toBe("/cvs/cv-new/edit"));
    expect(await screen.findByRole("heading", { name: "Edit CV" })).toBeInTheDocument();
    expect(textArea()).toHaveValue("# Me");
    expect(nameInput()).toHaveValue("My CV");
    expect(gets).toBe(0);
  });
});

describe("CvEditorPage — edit", () => {
  it("announces a load error as an alert", async () => {
    server.use(http.get(CV_URL, () => HttpResponse.json({ detail: "Not found" }, { status: 404 })));
    renderEditor("/cvs/cv-1/edit");

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "CV text" })).not.toBeInTheDocument();
  });

  it("loads the CV name and text and shows them formatted in the preview", async () => {
    renderEditor("/cvs/cv-1/edit");

    expect(await screen.findByDisplayValue("Software Engineer CV")).toBeInTheDocument();
    expect(textArea()).toHaveValue(mockCvs[0]!.content);
    const preview = screen.getByRole("region", { name: "Preview" });
    expect(within(preview).getByRole("heading", { name: "Test User" })).toBeInTheDocument();
    expect(within(preview).getByRole("heading", { name: "Summary" })).toBeInTheDocument();
  });

  it("sends the loaded version and keeps the returned one for the next save", async () => {
    const user = userEvent.setup();
    const patches: unknown[] = [];
    server.use(
      http.patch(CV_URL, async ({ request }) => {
        const body = (await request.json()) as { name: string; content: string; version: number };
        patches.push(body);
        return HttpResponse.json({ ...mockCvs[0]!, ...body, version: body.version + 1 });
      }),
    );
    renderEditor("/cvs/cv-1/edit");
    await screen.findByDisplayValue("Software Engineer CV");

    await user.type(textArea(), "\nGo");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("CV saved")).toBeInTheDocument();

    await user.type(textArea(), "!");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(patches).toHaveLength(2));
    const content = `${mockCvs[0]!.content}\nGo`;
    expect(patches).toEqual([
      { name: "Software Engineer CV", content, version: 3 },
      { name: "Software Engineer CV", content: `${content}!`, version: 4 },
    ]);
    // The draft stays in the editor after saving
    expect(textArea()).toHaveValue(`${content}!`);
  });

  it("keeps the user's text when saving fails", async () => {
    const user = userEvent.setup();
    server.use(http.patch(CV_URL, () => HttpResponse.json({ detail: "Boom" }, { status: 500 })));
    renderEditor("/cvs/cv-1/edit");
    await screen.findByDisplayValue("Software Engineer CV");

    await user.type(textArea(), "\nUnsaved");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.queryByText("CV saved")).not.toBeInTheDocument());
    expect(textArea()).toHaveValue(`${mockCvs[0]!.content}\nUnsaved`);
  });

  it("exports the current draft, unsaved changes included, to PDF", async () => {
    const user = userEvent.setup();
    renderEditor("/cvs/cv-1/edit");
    await screen.findByDisplayValue("Software Engineer CV");

    await user.clear(nameInput());
    await user.type(nameInput(), " Draft name ");
    await user.type(textArea(), "\nNot saved yet");
    await user.click(screen.getByRole("button", { name: "Export PDF" }));

    expect(downloadCvTextPdf).toHaveBeenCalledWith({
      name: "Draft name",
      content: `${mockCvs[0]!.content}\nNot saved yet`,
    });
  });

  it("shows no Export PDF button while the CV is loading", async () => {
    server.use(
      http.get(CV_URL, async () => {
        await delay(50);
        return HttpResponse.json(mockCvs[0]);
      }),
    );
    renderEditor("/cvs/cv-1/edit");

    expect(screen.getByText("Loading...")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Export PDF" })).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Export PDF" })).toBeInTheDocument();
  });

  it("sends one request when Save is double-clicked", async () => {
    const user = userEvent.setup();
    let patches = 0;
    server.use(
      http.patch(CV_URL, async ({ request }) => {
        patches += 1;
        const body = (await request.json()) as { version: number };
        await delay(50);
        return HttpResponse.json({ ...mockCvs[0]!, ...body, version: body.version + 1 });
      }),
    );
    renderEditor("/cvs/cv-1/edit");
    await screen.findByDisplayValue("Software Engineer CV");

    await user.type(textArea(), "!");
    await user.dblClick(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("CV saved")).toBeInTheDocument();
    expect(patches).toBe(1);
  });
});

describe("CvEditorPage — upload notice", () => {
  const NOTICE = "Text extracted from your file. Check the line breaks and save.";

  it("shows the notice after an upload, once, and a reload does not bring it back", async () => {
    const first = renderWithProviders(<CvEditorPage />, {
      initialEntries: [
        {
          pathname: "/cvs/cv-1/edit",
          state: { uploadNotice: { truncated: true, becameBase: false } },
        },
      ],
      path: "/cvs/:id/edit",
    });

    expect(screen.getByText(NOTICE)).toBeInTheDocument();
    expect(
      screen.getByText("The text was longer than 20 000 characters and was cut."),
    ).toBeInTheDocument();
    // The CV still loads under the notice, on the same URL
    expect(await screen.findByDisplayValue("Software Engineer CV")).toBeInTheDocument();
    await waitFor(() => expect(first.router.state.location.state).toBeNull());
    expect(first.router.state.location.pathname).toBe("/cvs/cv-1/edit");
    expect(screen.getByText(NOTICE)).toBeInTheDocument();

    const reloadAt = first.router.state.location;
    first.unmount();
    renderWithProviders(<CvEditorPage />, { initialEntries: [reloadAt], path: "/cvs/:id/edit" });
    expect(await screen.findByDisplayValue("Software Engineer CV")).toBeInTheDocument();
    expect(screen.queryByText(NOTICE)).not.toBeInTheDocument();
  });

  it("shows no notice when the editor is opened normally", async () => {
    renderEditor("/cvs/cv-1/edit");

    expect(await screen.findByDisplayValue("Software Engineer CV")).toBeInTheDocument();
    expect(screen.queryByText(NOTICE)).not.toBeInTheDocument();
  });
});

describe("CvEditorPage — text limit", () => {
  it("leaves a paste that fits to the browser, so undo keeps working", () => {
    renderEditor("/cvs/new");
    const field = textArea();
    field.focus();

    const notCancelled = fireEvent.paste(field, {
      clipboardData: { getData: () => "short text" },
    });

    expect(notCancelled).toBe(true);
  });

  it("intercepts a paste that does not fit", () => {
    renderEditor("/cvs/new");
    const field = textArea();
    fireEvent.change(field, { target: { value: "a".repeat(CV_CONTENT_MAX_LENGTH - 1) } });
    field.focus();
    field.setSelectionRange(field.value.length, field.value.length);

    const notCancelled = fireEvent.paste(field, {
      clipboardData: { getData: () => "bc" },
    });

    expect(notCancelled).toBe(false);
    expect(field.value).toHaveLength(CV_CONTENT_MAX_LENGTH);
  });

  it("cuts pasted text to the 20 000 character limit", async () => {
    const user = userEvent.setup();
    renderEditor("/cvs/new");
    const field = textArea();
    fireEvent.change(field, { target: { value: "a".repeat(CV_CONTENT_MAX_LENGTH - 10) } });

    field.focus();
    field.setSelectionRange(field.value.length, field.value.length);
    await user.paste("b".repeat(50));

    expect(field.value).toHaveLength(CV_CONTENT_MAX_LENGTH);
    expect(field.value.endsWith("a" + "b".repeat(10))).toBe(true);
  });

  it("counts the replaced selection as free room when pasting", async () => {
    const user = userEvent.setup();
    renderEditor("/cvs/new");
    const field = textArea();
    fireEvent.change(field, { target: { value: "x".repeat(CV_CONTENT_MAX_LENGTH) } });

    field.focus();
    field.setSelectionRange(0, 5);
    await user.paste("Hello world");

    expect(field.value).toHaveLength(CV_CONTENT_MAX_LENGTH);
    expect(field.value.startsWith("Hellox")).toBe(true);
  });
});

describe("insertTextWithinLimit", () => {
  it("inserts at the caret when there is room", () => {
    expect(insertTextWithinLimit("ac", "b", 1, 1, 10)).toEqual({ value: "abc", caret: 2 });
  });

  it("drops the whole paste when the text is already full", () => {
    expect(insertTextWithinLimit("abc", "zz", 3, 3, 3)).toEqual({ value: "abc", caret: 3 });
  });

  it("never splits a surrogate pair at the limit", () => {
    // "😀" is two UTF-16 units; only one unit of room is left
    expect(insertTextWithinLimit("ab", "😀", 2, 2, 3)).toEqual({ value: "ab", caret: 2 });
  });
});

describe("CvEditorPage — layout", () => {
  it("shows the editor and the preview side by side on wide screens", () => {
    mockPhoneWidth(false);
    renderEditor("/cvs/new");

    expect(textArea()).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Preview" })).toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: "Editor view" })).not.toBeInTheDocument();
  });

  it("uses Edit / Preview tabs on phone width, Edit first", async () => {
    mockPhoneWidth(true);
    const user = userEvent.setup();
    renderEditor("/cvs/new");

    const tabs = screen.getByRole("radiogroup", { name: "Editor view" });
    expect(within(tabs).getByRole("radio", { name: "Edit" })).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByRole("region", { name: "Preview" })).not.toBeInTheDocument();

    await user.type(textArea(), "## Skills");
    await user.click(within(tabs).getByRole("radio", { name: "Preview" }));

    expect(screen.queryByRole("textbox", { name: "CV text" })).not.toBeInTheDocument();
    const preview = screen.getByRole("region", { name: "Preview" });
    expect(within(preview).getByRole("heading", { name: "Skills" })).toBeInTheDocument();

    // The draft survives switching back
    await user.click(within(tabs).getByRole("radio", { name: "Edit" }));
    expect(textArea()).toHaveValue("## Skills");
  });
});
