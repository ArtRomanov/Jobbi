import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { CvEditorPage } from "@/pages/cv-editor";
import { downloadCvTextPdf } from "@/features/cv-pdf";
import { downloadCvHtml } from "@/features/cv-html-export";
import { CV_CONTENT_MAX_LENGTH } from "@/features/cv-text-editor";
import { insertTextWithinLimit } from "@/features/cv-text-editor/lib/insert-text-within-limit";
import { CvsPage } from "@/pages/cvs";
import { serveCvStore } from "./mocks/cv-store";
import { mockCvs } from "./mocks/handlers";
import { server } from "./setup";
import { renderWithProviders, type RenderWithProvidersResult } from "./utils";

vi.mock("@/features/cv-pdf", () => ({ downloadCvTextPdf: vi.fn().mockResolvedValue(undefined) }));
vi.mock("@/features/cv-html-export", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/features/cv-html-export")>()),
  downloadCvHtml: vi.fn().mockResolvedValue(undefined),
}));

const CVS_URL = "*/api/v1/cvs";
const CV_URL = "*/api/v1/cvs/:id";
const PLACEHOLDER = "Write your CV here, or upload a PDF/DOCX on the CVs page.";
const HINT = "# Heading · ## Section · **bold** · - list · [link](https://…)";
const HINT_DESCRIPTION =
  "Formatting: start a line with # for a heading, ## for a section, wrap text in two asterisks for bold, start a line with a dash for a list item, write links as text in square brackets followed by the address in parentheses.";
const PHONE_QUERY = "(max-width: 640px)";

function renderEditor(url: string) {
  // The same routes as the real router, so the post-save move to the list is real
  return renderWithProviders(<CvEditorPage />, {
    initialEntries: ["/cvs", url],
    path: "/cvs/new",
    routes: [
      { path: "/cvs/:id/edit", element: <CvEditorPage /> },
      { path: "/cvs", element: <CvsPage /> },
    ],
  });
}

/** The CVs page's row for a CV (its name is the row's first span). */
function rowOf(name: string): HTMLElement {
  return screen.getByText(name, { selector: "span" }).closest("li")!;
}

/** After a successful save: the CVs page, reached by a replace, with no leave prompt. */
async function expectBackOnCvsList(router: RenderWithProvidersResult["router"]): Promise<void> {
  await waitFor(() => expect(router.state.location.pathname).toBe("/cvs"));
  expect(router.state.historyAction).toBe("REPLACE");
  expect(await screen.findByRole("region", { name: "My CVs" })).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: "CV text" })).not.toBeInTheDocument();
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
  vi.mocked(downloadCvHtml).mockClear();
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
    const preview = screen.getByRole("region", { name: "CV preview" });

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

  it("creates the CV with the trimmed name and the text, then lands on the CVs list with it", async () => {
    const user = userEvent.setup();
    const store = serveCvStore();
    const { router } = renderEditor("/cvs/new");

    await user.type(nameInput(), "  My CV  ");
    await user.type(textArea(), "# Me");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await expectBackOnCvsList(router);
    expect(screen.getByText("CV saved")).toBeInTheDocument();
    expect(store.posts).toEqual([{ name: "My CV", content: "# Me", is_base: false }]);
    // The list is fetched fresh on arrival, so the new CV is in it
    expect(await screen.findByText("My CV", { selector: "span" })).toBeInTheDocument();
    expect(within(rowOf("My CV")).queryByText("Base")).not.toBeInTheDocument();
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
    const preview = screen.getByRole("region", { name: "CV preview" });
    expect(within(preview).getByRole("heading", { name: "Test User" })).toBeInTheDocument();
    expect(within(preview).getByRole("heading", { name: "Summary" })).toBeInTheDocument();
  });

  it("sends the loaded version, then lands on the CVs list with the saved name", async () => {
    const user = userEvent.setup();
    const store = serveCvStore();
    const { router } = renderEditor("/cvs/cv-1/edit");
    await screen.findByDisplayValue("Software Engineer CV");

    await user.clear(nameInput());
    await user.type(nameInput(), "Renamed CV");
    await user.type(textArea(), "\nGo");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await expectBackOnCvsList(router);
    expect(screen.getByText("CV saved")).toBeInTheDocument();
    expect(store.patches).toEqual([
      { name: "Renamed CV", content: `${mockCvs[0]!.content}\nGo`, version: 3 },
    ]);
    expect(await screen.findByText("Renamed CV", { selector: "span" })).toBeInTheDocument();
    expect(screen.queryByText("Software Engineer CV", { selector: "span" })).not.toBeInTheDocument();
  });

  it("keeps the user's text and stays on the editor when saving fails", async () => {
    const user = userEvent.setup();
    server.use(http.patch(CV_URL, () => HttpResponse.json({ detail: "Boom" }, { status: 500 })));
    const { router } = renderEditor("/cvs/cv-1/edit");
    await screen.findByDisplayValue("Software Engineer CV");

    await user.type(textArea(), "\nUnsaved");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not save the CV. Please try again.");
    expect(screen.queryByText("CV saved")).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/cvs/cv-1/edit");
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

  it("downloads the current draft as designed HTML", async () => {
    const user = userEvent.setup();
    renderEditor("/cvs/cv-1/edit");
    await screen.findByDisplayValue("Software Engineer CV");

    await user.type(textArea(), "\nNot saved yet");
    await user.click(screen.getByRole("button", { name: "Download HTML" }));

    expect(downloadCvHtml).toHaveBeenCalledWith({
      name: "Software Engineer CV",
      content: `${mockCvs[0]!.content}\nNot saved yet`,
    });
    expect(downloadCvTextPdf).not.toHaveBeenCalled();
  });

  it('says "Couldn\'t create the file." when the HTML download fails', async () => {
    const user = userEvent.setup();
    vi.mocked(downloadCvHtml).mockRejectedValueOnce(new Error("Disk full"));
    renderEditor("/cvs/cv-1/edit");
    await screen.findByDisplayValue("Software Engineer CV");

    await user.click(screen.getByRole("button", { name: "Download HTML" }));

    expect(await screen.findByText("Couldn't create the file.")).toBeInTheDocument();
    expect(screen.queryByText("Network error. Check your connection.")).not.toBeInTheDocument();
  });

  it("shows the preview in the designed layout: dates on the title row", async () => {
    const user = userEvent.setup();
    renderEditor("/cvs/new");

    await user.type(textArea(), "# Jane{enter}Engineer{enter}jane@example.com{enter}## Experience{enter}### Lead{enter}2020 – 2022{enter}- Did");

    const preview = screen.getByRole("region", { name: "CV preview" });
    await waitFor(() => {
      expect(within(preview).getByRole("heading", { level: 4, name: "Lead" })).toBeInTheDocument();
    });
    // The page owns the h1: the CV name is an h2 here
    expect(within(preview).getByRole("heading", { level: 2, name: "Jane" })).toBeInTheDocument();
    const titleRow = within(preview).getByRole("heading", { level: 4, name: "Lead" }).parentElement!;
    expect(titleRow).toHaveClass("cv-entry-head");
    // A boundary stays between title and dates in the text (not "Lead2020")
    expect(titleRow).toHaveTextContent("Lead 2020 – 2022");
    expect(within(preview).getByRole("link", { name: /jane@example.com/ })).toHaveAttribute("target", "_blank");
  });

  it("shows no Download HTML button on a new CV", () => {
    renderEditor("/cvs/new");
    expect(screen.queryByRole("button", { name: "Download HTML" })).not.toBeInTheDocument();
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

describe("CvEditorPage — Base CV switch", () => {
  const HELP = 'Tailoring with "Add & tailor CV" starts from your base CV.';

  function baseSwitch(): HTMLInputElement {
    return screen.getByRole("switch", { name: "Set as base CV for every application" }) as HTMLInputElement;
  }

  function saveButton(): HTMLButtonElement {
    return screen.getByRole("button", { name: "Save" }) as HTMLButtonElement;
  }

  it("starts from is_base, with its helper text; off for a new CV", async () => {
    const first = renderEditor("/cvs/cv-1/edit");
    await screen.findByDisplayValue("Software Engineer CV");
    expect(baseSwitch()).toBeChecked();
    expect(baseSwitch()).toHaveAccessibleDescription(HELP);
    first.unmount();

    renderEditor("/cvs/new");
    expect(baseSwitch()).not.toBeChecked();
  });

  it("changing only the switch enables Save; switching back disables it", async () => {
    const user = userEvent.setup();
    renderEditor("/cvs/cv-2/edit");
    await screen.findByDisplayValue("Frontend Developer CV");

    expect(saveButton()).toHaveAttribute("aria-disabled", "true");
    await user.click(baseSwitch());
    expect(saveButton()).not.toHaveAttribute("aria-disabled");
    await user.click(baseSwitch());
    expect(saveButton()).toHaveAttribute("aria-disabled", "true");
  });

  it("switched on: PATCH sends is_base true, base toast, and the list shows it as Base", async () => {
    const user = userEvent.setup();
    const store = serveCvStore();
    const { router } = renderEditor("/cvs/cv-2/edit");
    await screen.findByDisplayValue("Frontend Developer CV");
    expect(screen.queryByText("Base")).not.toBeInTheDocument();

    await user.click(baseSwitch());
    await user.click(saveButton());

    await expectBackOnCvsList(router);
    expect(screen.getByText("CV saved and set as your base CV")).toBeInTheDocument();
    expect(store.patches).toEqual([
      {
        name: "Frontend Developer CV",
        content: mockCvs[1]!.content,
        version: mockCvs[1]!.version,
        is_base: true,
      },
    ]);
    // Fresh list: the base moved to this CV
    await screen.findByText("Frontend Developer CV", { selector: "span" });
    expect(within(rowOf("Frontend Developer CV")).getByText("Base")).toBeInTheDocument();
    expect(within(rowOf("Software Engineer CV")).queryByText("Base")).not.toBeInTheDocument();
  });

  it("switched off on the base: PATCH sends is_base false, says there is no base now", async () => {
    const user = userEvent.setup();
    const store = serveCvStore();
    const { router } = renderEditor("/cvs/cv-1/edit");
    await screen.findByDisplayValue("Software Engineer CV");
    expect(screen.getByText("Base")).toBeInTheDocument();

    await user.click(baseSwitch());
    await user.click(saveButton());

    await expectBackOnCvsList(router);
    expect(screen.getByText("CV saved. You have no base CV now.")).toBeInTheDocument();
    expect(store.patches[0]).toMatchObject({ is_base: false });
    await screen.findByText("Software Engineer CV", { selector: "span" });
    expect(screen.queryByText("Base")).not.toBeInTheDocument();
  });

  it("a text-only save leaves is_base out of the PATCH and shows the plain toast", async () => {
    const user = userEvent.setup();
    const store = serveCvStore();
    const { router } = renderEditor("/cvs/cv-1/edit");
    await screen.findByDisplayValue("Software Engineer CV");

    await user.type(textArea(), "!");
    await user.click(saveButton());

    await expectBackOnCvsList(router);
    expect(screen.getByText("CV saved")).toBeInTheDocument();
    expect(store.patches[0]).not.toHaveProperty("is_base");
    await screen.findByText("Software Engineer CV", { selector: "span" });
    expect(within(rowOf("Software Engineer CV")).getByText("Base")).toBeInTheDocument();
  });

  it("base changed elsewhere: a text-only save says just CV saved", async () => {
    const user = userEvent.setup();
    // cv-1 was the base when opened; another CV became the base meanwhile
    const patches: Record<string, unknown>[] = [];
    server.use(
      http.patch(CV_URL, async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown> & { version: number };
        patches.push(body);
        const { version, ...changes } = body;
        return HttpResponse.json({ ...mockCvs[0]!, ...changes, is_base: false, version: version + 1 });
      }),
    );
    const { router } = renderEditor("/cvs/cv-1/edit");
    await screen.findByDisplayValue("Software Engineer CV");
    expect(baseSwitch()).toBeChecked();

    await user.type(textArea(), "!");
    await user.click(saveButton());

    await expectBackOnCvsList(router);
    expect(screen.getByText("CV saved")).toBeInTheDocument();
    expect(patches[0]).not.toHaveProperty("is_base");
    expect(screen.queryByText("CV saved. You have no base CV now.")).not.toBeInTheDocument();
  });

  it("a new CV with the switch on is created as the base", async () => {
    const user = userEvent.setup();
    const store = serveCvStore();
    const { router } = renderEditor("/cvs/new");

    await user.type(nameInput(), "Mine");
    await user.click(baseSwitch());
    await user.click(saveButton());

    await expectBackOnCvsList(router);
    expect(screen.getByText("CV saved and set as your base CV")).toBeInTheDocument();
    expect(store.posts).toEqual([{ name: "Mine", content: "", is_base: true }]);
    await screen.findByText("Mine", { selector: "span" });
    expect(within(rowOf("Mine")).getByText("Base")).toBeInTheDocument();
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
    expect(screen.getByRole("region", { name: "CV preview" })).toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: "Editor view" })).not.toBeInTheDocument();
  });

  it("gives the text and the preview the same fixed-height box that scrolls inside", () => {
    mockPhoneWidth(false);
    renderEditor("/cvs/new");

    const preview = screen.getByRole("region", { name: "CV preview" });
    const text = textArea();
    expect(preview.style.height).not.toBe("");
    expect(preview.style.height).toBe(text.style.height);
    expect(preview.style.overflowY).toBe("auto");
    expect(text.style.overflowY).toBe("auto");
    for (const prop of ["padding", "border", "borderRadius", "backgroundColor"] as const) {
      expect(preview.style[prop]).toBe(text.style[prop]);
    }
    // A scrollable region must be reachable by keyboard
    expect(preview).toHaveAttribute("tabindex", "0");
    preview.focus();
    expect(preview).toHaveFocus();
  });

  it("uses the same preview box on the phone Preview tab", async () => {
    mockPhoneWidth(true);
    const user = userEvent.setup();
    renderEditor("/cvs/new");

    const textHeight = textArea().style.height;
    const tabs = screen.getByRole("radiogroup", { name: "Editor view" });
    await user.click(within(tabs).getByRole("radio", { name: "Preview" }));

    const preview = screen.getByRole("region", { name: "CV preview" });
    expect(preview.style.height).toBe(textHeight);
    expect(preview.style.overflowY).toBe("auto");
    expect(preview).toHaveAttribute("tabindex", "0");
  });

  it("uses Edit / Preview tabs on phone width, Edit first", async () => {
    mockPhoneWidth(true);
    const user = userEvent.setup();
    renderEditor("/cvs/new");

    const tabs = screen.getByRole("radiogroup", { name: "Editor view" });
    expect(within(tabs).getByRole("radio", { name: "Edit" })).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByRole("region", { name: "CV preview" })).not.toBeInTheDocument();

    await user.type(textArea(), "## Skills");
    await user.click(within(tabs).getByRole("radio", { name: "Preview" }));

    expect(screen.queryByRole("textbox", { name: "CV text" })).not.toBeInTheDocument();
    const preview = screen.getByRole("region", { name: "CV preview" });
    expect(within(preview).getByRole("heading", { name: "Skills" })).toBeInTheDocument();

    // The draft survives switching back
    await user.click(within(tabs).getByRole("radio", { name: "Edit" }));
    expect(textArea()).toHaveValue("## Skills");
  });
});
