import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { InboxPage } from "@/pages/inbox";
import { renderWithProviders } from "./utils";
import { mockVacancySourcesEmpty } from "./mocks/handlers";
import { server } from "./setup";

const SOURCES_URL = "*/api/v1/vacancy-sources";
const SETTINGS_URL = "*/api/v1/vacancy-search-settings";
const HINT = "Describe what you're looking for to start finding vacancies.";

function serveSettings(description: string | null): void {
  server.use(
    http.get(SOURCES_URL, () =>
      HttpResponse.json({ ...mockVacancySourcesEmpty, settings: { description } }),
    ),
  );
}

function getDescription(): HTMLElement {
  return screen.getByRole("textbox", { name: "Search description" });
}

function getSave(): HTMLElement {
  return screen.getByRole("button", { name: "Save" });
}

function getSettingsSection(): HTMLElement {
  return screen.getByRole("region", { name: "What are you looking for?" });
}

async function renderLoaded(): Promise<void> {
  renderWithProviders(<InboxPage />);
  await waitFor(() => expect(getDescription()).toBeEnabled());
}

describe("Search settings in the Sources panel", () => {
  it("keeps the form disabled until settings load, then fills it", async () => {
    serveSettings("Senior frontend, React");
    renderWithProviders(<InboxPage />);

    expect(getDescription()).toBeDisabled();
    expect(getSave()).toBeDisabled();
    expect(screen.queryByText(HINT)).not.toBeInTheDocument();

    await waitFor(() => expect(getDescription()).toBeEnabled());
    expect(getDescription()).toHaveValue("Senior frontend, React");
    expect(screen.getByText("22/500")).toBeInTheDocument();
    expect(getSave()).toBeEnabled();
    expect(screen.queryByText(HINT)).not.toBeInTheDocument();
  });

  it("has only the description field and sends only the description", async () => {
    serveSettings("Frontend");
    const bodies: unknown[] = [];
    server.use(
      http.patch(SETTINGS_URL, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ description: "Frontend React" });
      }),
    );
    const user = userEvent.setup();
    await renderLoaded();

    const section = getSettingsSection();
    expect(within(section).getAllByRole("textbox")).toEqual([getDescription()]);
    expect(screen.queryByRole("textbox", { name: "Exclude words" })).not.toBeInTheDocument();
    expect(screen.queryByText(/exclude/i)).not.toBeInTheDocument();

    await user.type(getDescription(), " React");
    await user.click(getSave());

    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(bodies).toEqual([{ description: "Frontend React" }]);
    expect(screen.queryByText(/exclude/i)).not.toBeInTheDocument();
  });

  it("updates the counter as the user types", async () => {
    const user = userEvent.setup();
    await renderLoaded();
    expect(screen.getByText("0/500")).toBeInTheDocument();

    await user.type(getDescription(), "React");

    expect(screen.getByText("5/500")).toBeInTheDocument();
    expect(getDescription()).toHaveAccessibleDescription("5/500");
  });

  it("stops typing at 500 characters", async () => {
    serveSettings("a".repeat(498));
    const user = userEvent.setup();
    await renderLoaded();

    await user.type(getDescription(), "bcdef");

    expect(getDescription()).toHaveValue(`${"a".repeat(498)}bc`);
    expect(screen.getByText("500/500")).toBeInTheDocument();
  });

  it("cuts pasted text to 500 characters", async () => {
    const user = userEvent.setup();
    await renderLoaded();

    await user.click(getDescription());
    await user.paste("x".repeat(620));

    expect(getDescription()).toHaveValue("x".repeat(500));
    expect(screen.getByText("500/500")).toBeInTheDocument();
  });

  it("saves only the description and shows the server-normalized value", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.patch(SETTINGS_URL, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ description: "Senior React" });
      }),
    );
    const user = userEvent.setup();
    await renderLoaded();

    await user.type(getDescription(), "  Senior React  ");
    await user.click(getSave());

    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(bodies).toEqual([{ description: "  Senior React  " }]);
    expect(getDescription()).toHaveValue("Senior React");
    expect(screen.getByText("12/500")).toBeInTheDocument();
    await waitFor(() => expect(getSave()).toHaveFocus());
  });

  it("sends a blank description as null and uses the default normalizing handler", async () => {
    serveSettings("Old");
    const bodies: unknown[] = [];
    server.events.on("request:start", async ({ request }) => {
      if (request.method === "PATCH") bodies.push(await request.clone().json());
    });
    const user = userEvent.setup();
    await renderLoaded();

    await user.clear(getDescription());
    await user.type(getDescription(), "   ");
    await user.click(getSave());

    expect(await screen.findByText("Saved")).toBeInTheDocument();
    server.events.removeAllListeners();
    expect(bodies).toEqual([{ description: null }]);
    expect(getDescription()).toHaveValue("");
    expect(screen.getByText(HINT)).toBeInTheDocument();
  });

  it("shows a 400 error inline and keeps the drafts", async () => {
    server.use(
      http.patch(SETTINGS_URL, () =>
        HttpResponse.json({ detail: "Description is too long" }, { status: 400 }),
      ),
    );
    const user = userEvent.setup();
    await renderLoaded();

    await user.type(getDescription(), "Frontend");
    await user.click(getSave());

    expect(await screen.findByRole("alert")).toHaveTextContent("Description is too long");
    expect(getDescription()).toHaveValue("Frontend");
    expect(screen.queryByText("Saved")).not.toBeInTheDocument();
    expect(getSave()).toHaveFocus();
    // Still no saved description
    expect(screen.getByText(HINT)).toBeInTheDocument();

    await user.type(getDescription(), "!");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows the hint while no description is saved, even while typing, and hides it after save", async () => {
    const user = userEvent.setup();
    await renderLoaded();
    expect(screen.getByText(HINT)).toBeInTheDocument();

    await user.type(getDescription(), "Senior frontend");
    expect(screen.getByText(HINT)).toBeInTheDocument();

    await user.click(getSave());
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(screen.queryByText(HINT)).not.toBeInTheDocument();
  });

  it("shows a loading Save button while the request runs", async () => {
    let release = (): void => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.patch(SETTINGS_URL, async () => {
        await gate;
        return HttpResponse.json({ description: "Frontend" });
      }),
    );
    const user = userEvent.setup();
    await renderLoaded();

    await user.type(getDescription(), "Frontend");
    await user.click(getSave());

    expect(getSave()).toHaveAttribute("aria-busy", "true");
    expect(getSave()).toBeDisabled();
    release();
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(getSave()).toBeEnabled();
  });
});
