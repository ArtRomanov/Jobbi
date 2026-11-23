import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { CvEditorPage } from "@/pages/cv-editor";
import type { Cv } from "@/entities/cv";
import { mockCvs } from "./mocks/handlers";
import { server } from "./setup";
import { renderWithProviders } from "./utils";

vi.mock("@/features/cv-pdf", () => ({ downloadCvTextPdf: vi.fn().mockResolvedValue(undefined) }));

const CV_URL = "*/api/v1/cvs/:id";

function serveCv(cv: Cv): void {
  server.use(http.get(CV_URL, () => HttpResponse.json(cv)));
}

function renderEditor(url: string) {
  return renderWithProviders(<CvEditorPage />, {
    initialEntries: [url],
    path: "/cvs/new",
    routes: [{ path: "/cvs/:id/edit", element: <CvEditorPage /> }],
  });
}

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
});

describe("CV editor header (spec 011 §2.1)", () => {
  it("shows the Base label for the base CV", async () => {
    serveCv(mockCvs[0]!);
    renderEditor("/cvs/cv-1/edit");

    await screen.findByDisplayValue("Software Engineer CV");
    expect(screen.getByText("Base")).toBeInTheDocument();
    expect(screen.queryByText(/Tailored for/)).not.toBeInTheDocument();
  });

  it("shows no label for an ordinary own CV", async () => {
    serveCv(mockCvs[1]!);
    renderEditor("/cvs/cv-2/edit");

    await screen.findByDisplayValue("Frontend Developer CV");
    expect(screen.queryByText("Base")).not.toBeInTheDocument();
    expect(screen.queryByText(/Tailored for/)).not.toBeInTheDocument();
  });

  it("shows the application a tailored copy was made for, linking to the dashboard", async () => {
    serveCv(mockCvs[2]!);
    renderEditor("/cvs/cv-3/edit");

    await screen.findByDisplayValue(mockCvs[2]!.name);
    expect(screen.getByText(/Tailored for:/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Acme Corp — Senior Engineer" })).toHaveAttribute(
      "href",
      "/dashboard?application=app-1",
    );
    expect(screen.queryByText("Base")).not.toBeInTheDocument();
  });

  it("shows Application deleted for a tailored copy whose application is gone", async () => {
    serveCv({ ...mockCvs[2]!, tailored_application_deleted: true });
    renderEditor("/cvs/cv-3/edit");

    await screen.findByDisplayValue(mockCvs[2]!.name);
    expect(screen.getByText("Application deleted")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Acme Corp/ })).not.toBeInTheDocument();
  });

  it("shows nothing on a new CV", () => {
    renderEditor("/cvs/new");

    expect(screen.queryByText("Base")).not.toBeInTheDocument();
    expect(screen.queryByText(/Tailored for/)).not.toBeInTheDocument();
  });
});
