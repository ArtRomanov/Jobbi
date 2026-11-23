import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useLocation } from "react-router-dom";
import { UploadCvButton, UploadNotice } from "@/features/cv-upload";
import { server } from "./setup";
import { renderWithProviders } from "./utils";

const UPLOAD_URL = "http://localhost:8000/api/v1/cvs/upload";

const uploadedCv = {
  id: "cv-new",
  name: "resume",
  content: "Ivan Petrov",
  version: 1,
  linked_applications_count: 0,
  created_at: "2026-11-23T10:00:00Z",
  updated_at: "2026-11-23T10:00:00Z",
  is_base: false,
  kind: "own",
  tailored_for: null,
  tailored_application_deleted: false,
  became_base: false,
  truncated: false,
};

function pdfFile(name = "resume.pdf", size?: number): File {
  const file = new File(["%PDF-1.4 test"], name, { type: "application/pdf" });
  if (size !== undefined) Object.defineProperty(file, "size", { value: size });
  return file;
}

/** Router state each EditorStub render saw (the notice clears it right away). */
let editorStates: unknown[] = [];

/** Editor stand-in: shows the notice and records the router state it received. */
function EditorStub() {
  const location = useLocation();
  editorStates.push(location.state);
  return (
    <div>
      <p>Editor {location.pathname}</p>
      <UploadNotice />
    </div>
  );
}

function renderButton() {
  return renderWithProviders(<UploadCvButton />, {
    initialEntries: ["/cvs"],
    path: "/cvs",
    routes: [{ path: "/cvs/:id/edit", element: <EditorStub /> }],
  });
}

function fileInput(): HTMLInputElement {
  return screen.getByTestId("cv-upload-input");
}

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
  editorStates = [];
});

describe("UploadCvButton", () => {
  it("renders a button and a hidden one-file input for PDF and DOCX", () => {
    renderButton();

    expect(screen.getByRole("button", { name: "Upload CV" })).toBeEnabled();
    const input = fileInput();
    expect(input).toHaveAttribute("accept", ".pdf,.docx");
    expect(input).not.toHaveAttribute("multiple");
    expect(input.hidden).toBe(true);
  });

  it("sends the file as multipart and opens the editor with the notice", async () => {
    let received: FormDataEntryValue | null = null;
    let auth: string | null = null;
    server.use(
      http.post(UPLOAD_URL, async ({ request }) => {
        auth = request.headers.get("Authorization");
        received = (await request.formData()).get("file");
        return HttpResponse.json(uploadedCv, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    const { router } = renderButton();

    await user.upload(fileInput(), pdfFile());

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/cvs/cv-new/edit");
    });
    expect(editorStates[0]).toEqual({
      uploadNotice: { truncated: false, becameBase: false },
    });
    expect(auth).toBe("Bearer test-token");
    expect(received).toBeInstanceOf(File);
    expect((received as unknown as File).name).toBe("resume.pdf");
    expect(
      screen.getByText("Text extracted from your file. Check the line breaks and save."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/was cut/)).not.toBeInTheDocument();
    expect(screen.queryByText(/base CV/)).not.toBeInTheDocument();
  });

  it("an upload that became the base adds the base line to the notice", async () => {
    server.use(
      http.post(UPLOAD_URL, () =>
        HttpResponse.json({ ...uploadedCv, is_base: true, became_base: true }, { status: 201 }),
      ),
    );
    const user = userEvent.setup();
    const { router } = renderButton();

    await user.upload(fileInput(), pdfFile());

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/cvs/cv-new/edit");
    });
    expect(editorStates[0]).toEqual({ uploadNotice: { truncated: false, becameBase: true } });
    expect(screen.getByRole("status")).toHaveTextContent("This CV is now your base CV.");
    expect(screen.queryByText(/was cut/)).not.toBeInTheDocument();
  });

  it("passes the cut flag on, and the notice shows the cut line", async () => {
    server.use(
      http.post(UPLOAD_URL, () =>
        HttpResponse.json({ ...uploadedCv, truncated: true }, { status: 201 }),
      ),
    );
    const user = userEvent.setup();
    renderButton();

    await user.upload(fileInput(), pdfFile());

    expect(
      await screen.findByText(
        "The text was longer than 20 000 characters and was cut.",
      ),
    ).toBeInTheDocument();
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
        return HttpResponse.json(uploadedCv, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    const { router } = renderButton();

    await user.upload(fileInput(), pdfFile());

    const busy = await screen.findByRole("button", { name: "Uploading…" });
    expect(busy).toBeDisabled();
    await user.click(busy);
    expect(calls).toBe(1);

    release();
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/cvs/cv-new/edit");
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
    expect(screen.getByRole("button", { name: "Upload CV" })).toBeEnabled();
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
        return HttpResponse.json(uploadedCv, { status: 201 });
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
  it("renders nothing without upload state", () => {
    renderWithProviders(<UploadNotice />);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("is shown once: clears the router state, and a reload shows nothing", async () => {
    const entry = {
      pathname: "/cvs/1/edit",
      search: "?x=1",
      state: { uploadNotice: { truncated: false, becameBase: false } },
    };
    const first = renderWithProviders(<UploadNotice />, { initialEntries: [entry] });

    expect(screen.getByRole("status")).toHaveTextContent("Text extracted from your file.");
    await waitFor(() => {
      expect(first.router.state.location.state).toBeNull();
    });
    // Same URL, replaced in place, and the notice stays up for this visit
    expect(first.router.state.location.pathname).toBe("/cvs/1/edit");
    expect(first.router.state.location.search).toBe("?x=1");
    expect(first.router.state.historyAction).toBe("REPLACE");
    expect(screen.getByRole("status")).toBeInTheDocument();

    // A reload restores the (now empty) history entry
    const reloadAt = first.router.state.location;
    first.unmount();
    renderWithProviders(<UploadNotice />, { initialEntries: [reloadAt] });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("adds the base line when the CV became the base", () => {
    renderWithProviders(<UploadNotice />, {
      initialEntries: [
        { pathname: "/cvs/1/edit", state: { uploadNotice: { truncated: true, becameBase: true } } },
      ],
    });

    const notice = screen.getByRole("status");
    expect(notice).toHaveTextContent("Text extracted from your file.");
    expect(notice).toHaveTextContent("was cut.");
    expect(notice).toHaveTextContent("This CV is now your base CV.");
  });
});
