import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { UploadCvButton, UploadNotice } from "@/features/cv-upload";
import { CvEditorPage } from "@/pages/cv-editor";
import { mockUploadDraft } from "./mocks/handlers";
import { server } from "./setup";
import { renderWithProviders } from "./utils";

vi.mock("@/features/cv-pdf", () => ({ downloadCvTextPdf: vi.fn().mockResolvedValue(undefined) }));

const UPLOAD_URL = "http://localhost:8000/api/v1/cvs/upload";
const CVS_URL = "http://localhost:8000/api/v1/cvs";
const NOTICE = "Text extracted from your file. Review it and save to add it to your CVs.";
const CUT_LINE = "The text was longer than 20 000 characters and was cut.";
const LEAVE_PROMPT = "You have unsaved changes. Leave without saving?";

function pdfFile(name = "resume.pdf", size?: number): File {
  const file = new File(["%PDF-1.4 test"], name, { type: "application/pdf" });
  if (size !== undefined) Object.defineProperty(file, "size", { value: size });
  return file;
}

/** Bodies of every `POST /cvs` (creating a CV); an upload must add none. */
let creates: unknown[] = [];

/** The CVs page's upload button at /cvs, the real editor at /cvs/new and /cvs/:id/edit. */
function renderButton() {
  return renderWithProviders(<UploadCvButton />, {
    initialEntries: ["/cvs"],
    path: "/cvs",
    routes: [
      { path: "/cvs/new", element: <CvEditorPage /> },
      { path: "/cvs/:id/edit", element: <CvEditorPage /> },
    ],
  });
}

function fileInput(): HTMLInputElement {
  return screen.getByTestId("cv-upload-input");
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

function baseSwitch(): HTMLInputElement {
  return screen.getByRole("switch", { name: "Base CV" }) as HTMLInputElement;
}

/** Upload a file and wait for the draft to open in the editor. */
async function uploadDraft(user: ReturnType<typeof userEvent.setup>) {
  const result = renderButton();
  await user.upload(fileInput(), pdfFile());
  await screen.findByDisplayValue(mockUploadDraft.name);
  return result;
}

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
  creates = [];
  server.use(
    http.post(CVS_URL, async ({ request }) => {
      const body = (await request.json()) as { name: string; content: string; is_base?: boolean };
      creates.push(body);
      return HttpResponse.json(
        {
          id: "cv-new",
          name: body.name,
          content: body.content,
          version: 1,
          linked_applications_count: 0,
          created_at: "2026-11-23T10:00:00Z",
          updated_at: "2026-11-23T10:00:00Z",
          is_base: body.is_base === true,
          kind: "own",
          tailored_for: null,
          tailored_application_deleted: false,
        },
        { status: 201 },
      );
    }),
  );
});

describe("UploadCvButton", () => {
  it("renders a button and a hidden one-file input for PDF and DOCX", () => {
    renderButton();

    expect(screen.getByRole("button", { name: "Upload CV" })).not.toHaveAttribute("aria-disabled");
    const input = fileInput();
    expect(input).toHaveAttribute("accept", ".pdf,.docx");
    expect(input).not.toHaveAttribute("multiple");
    expect(input.hidden).toBe(true);
  });

  it("sends the file as multipart and opens the text as an unsaved draft — nothing is created", async () => {
    let received: FormDataEntryValue | null = null;
    let auth: string | null = null;
    server.use(
      http.post(UPLOAD_URL, async ({ request }) => {
        auth = request.headers.get("Authorization");
        received = (await request.formData()).get("file");
        return HttpResponse.json(mockUploadDraft);
      }),
    );
    const user = userEvent.setup();
    const { router } = await uploadDraft(user);

    expect(router.state.location.pathname).toBe("/cvs/new");
    expect(auth).toBe("Bearer test-token");
    expect(received).toBeInstanceOf(File);
    expect((received as unknown as File).name).toBe("resume.pdf");

    expect(nameInput()).toHaveValue(mockUploadDraft.name);
    expect(textArea()).toHaveValue(mockUploadDraft.content);
    expect(screen.getByRole("status")).toHaveTextContent(NOTICE);
    expect(screen.queryByText(CUT_LINE)).not.toBeInTheDocument();
    // The old "This CV is now your base CV." line is gone
    expect(screen.queryByText(/now your base CV/)).not.toBeInTheDocument();
    // The draft is unsaved: Save is active, the switch starts off
    expect(saveButton()).not.toHaveAttribute("aria-disabled");
    expect(baseSwitch()).not.toBeChecked();
    expect(creates).toEqual([]);
  });

  it("clears the draft from router state, so a reload opens an empty new CV", async () => {
    const user = userEvent.setup();
    const first = await uploadDraft(user);

    await waitFor(() => expect(first.router.state.location.state).toBeNull());
    expect(first.router.state.location.pathname).toBe("/cvs/new");
    // The replace neither prompts nor loses the draft
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(textArea()).toHaveValue(mockUploadDraft.content);
    expect(screen.getByRole("status")).toHaveTextContent(NOTICE);

    const reloadAt = first.router.state.location;
    first.unmount();
    renderWithProviders(<CvEditorPage />, { initialEntries: [reloadAt], path: "/cvs/new" });

    expect(nameInput()).toHaveValue("");
    expect(textArea()).toHaveValue("");
    expect(screen.queryByText(NOTICE)).not.toBeInTheDocument();
    expect(saveButton()).toHaveAttribute("aria-disabled", "true");
  });

  it("asks before leaving the draft; Leave discards it and creates nothing", async () => {
    const user = userEvent.setup();
    const { router } = await uploadDraft(user);
    await waitFor(() => expect(router.state.location.state).toBeNull());

    await act(async () => {
      await router.navigate("/cvs");
    });
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(LEAVE_PROMPT);

    await user.click(within(dialog).getByRole("button", { name: "Leave" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/cvs"));
    expect(screen.getByRole("button", { name: "Upload CV" })).toBeInTheDocument();
    expect(creates).toEqual([]);
  });

  it("Stay keeps the draft in the editor", async () => {
    const user = userEvent.setup();
    const { router } = await uploadDraft(user);

    await act(async () => {
      await router.navigate("/cvs");
    });
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Stay" }));

    expect(router.state.location.pathname).toBe("/cvs/new");
    expect(textArea()).toHaveValue(mockUploadDraft.content);
    expect(screen.getByRole("status")).toHaveTextContent(NOTICE);
    expect(creates).toEqual([]);
  });

  it("saving the draft creates the CV (not as base) and opens its edit URL", async () => {
    const user = userEvent.setup();
    const { router } = await uploadDraft(user);

    await user.click(saveButton());

    expect(await screen.findByText("CV saved")).toBeInTheDocument();
    expect(creates).toEqual([
      { name: mockUploadDraft.name, content: mockUploadDraft.content, is_base: false },
    ]);
    await waitFor(() => expect(router.state.location.pathname).toBe("/cvs/cv-new/edit"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByText(NOTICE)).not.toBeInTheDocument();
    expect(saveButton()).toHaveAttribute("aria-disabled", "true");
    expect(textArea()).toHaveValue(mockUploadDraft.content);
  });

  it("the draft's switch turned on makes the new CV the base", async () => {
    const user = userEvent.setup();
    await uploadDraft(user);

    await user.click(baseSwitch());
    await user.click(saveButton());

    expect(await screen.findByText("CV saved and set as your base CV")).toBeInTheDocument();
    expect(creates).toEqual([
      { name: mockUploadDraft.name, content: mockUploadDraft.content, is_base: true },
    ]);
    // The header's "Base" label follows the saved CV
    expect(screen.getByText("Base")).toBeInTheDocument();
  });

  it("passes the cut flag on, and the notice shows the cut line", async () => {
    server.use(
      http.post(UPLOAD_URL, () => HttpResponse.json({ ...mockUploadDraft, truncated: true })),
    );
    const user = userEvent.setup();
    await uploadDraft(user);

    expect(screen.getByRole("status")).toHaveTextContent(CUT_LINE);
  });

  it('shows "Uploading…" and is disabled while the upload runs', async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    let calls = 0;
    server.use(
      http.post(UPLOAD_URL, async () => {
        calls += 1;
        await gate;
        return HttpResponse.json(mockUploadDraft);
      }),
    );
    const user = userEvent.setup();
    const { router } = renderButton();

    await user.upload(fileInput(), pdfFile());

    const busy = await screen.findByRole("button", { name: "Uploading…" });
    expect(busy).toHaveAttribute("aria-disabled", "true");
    // Still focusable (no `disabled`), so keyboard focus is not lost
    expect(busy).not.toBeDisabled();
    busy.focus();
    expect(busy).toHaveFocus();
    const pickerOpened = vi.spyOn(fileInput(), "click");
    await user.click(busy);
    expect(pickerOpened).not.toHaveBeenCalled();
    expect(calls).toBe(1);

    release();
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/cvs/new");
    });
  });

  it.each([
    [415, "UNSUPPORTED_FILE", "Upload a PDF or DOCX file."],
    [413, "FILE_TOO_LARGE", "The file is larger than 5 MB."],
    [
      422,
      "NO_TEXT",
      "Could not read text from this file. Upload a PDF with selectable text or a DOCX.",
    ],
    [400, "UPLOAD_FAILED", "Could not upload this file. Please try again."],
    [400, "SOMETHING_NEW", "Could not upload this file. Please try again."],
    [500, "Internal Server Error", "Could not upload this file. Please try again."],
  ])("maps %i %s to its message and stays on the page", async (status, detail, text) => {
    server.use(
      http.post(UPLOAD_URL, () => HttpResponse.json({ detail }, { status })),
    );
    const user = userEvent.setup();
    const { router } = renderButton();

    await user.upload(fileInput(), pdfFile());

    expect(await screen.findByText(text)).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/cvs");
    expect(screen.getByRole("button", { name: "Upload CV" })).not.toHaveAttribute("aria-disabled");
    expect(creates).toEqual([]);
  });

  it("shows the generic message on a network error", async () => {
    server.use(http.post(UPLOAD_URL, () => HttpResponse.error()));
    const user = userEvent.setup();
    renderButton();

    await user.upload(fileInput(), pdfFile());

    expect(
      await screen.findByText("Could not upload this file. Please try again."),
    ).toBeInTheDocument();
  });

  it("refuses a file over 5 MB without sending it", async () => {
    let calls = 0;
    server.use(
      http.post(UPLOAD_URL, () => {
        calls += 1;
        return HttpResponse.json(mockUploadDraft);
      }),
    );
    const user = userEvent.setup();
    renderButton();

    await user.upload(fileInput(), pdfFile("big.pdf", 5 * 1024 * 1024 + 1));

    expect(await screen.findByText("The file is larger than 5 MB.")).toBeInTheDocument();
    expect(calls).toBe(0);
  });
});

describe("UploadNotice", () => {
  it("shows the draft notice without the cut line", () => {
    renderWithProviders(<UploadNotice truncated={false} />);

    expect(screen.getByRole("status")).toHaveTextContent(NOTICE);
    expect(screen.queryByText(CUT_LINE)).not.toBeInTheDocument();
  });

  it("adds the cut line when the text was cut", () => {
    renderWithProviders(<UploadNotice truncated />);

    expect(screen.getByRole("status")).toHaveTextContent(CUT_LINE);
  });
});

describe("CvEditorPage — no upload draft", () => {
  it("ignores router state that is not a draft and opens an empty new CV", () => {
    renderWithProviders(<CvEditorPage />, {
      initialEntries: [{ pathname: "/cvs/new", state: { uploadDraft: { name: 1 } } }],
      path: "/cvs/new",
    });

    expect(nameInput()).toHaveValue("");
    expect(screen.queryByText(NOTICE)).not.toBeInTheDocument();
  });
});
