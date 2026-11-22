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

function serveSettings(description: string | null, exclude: string[]): void {
  server.use(
    http.get(SOURCES_URL, () =>
      HttpResponse.json({ ...mockVacancySourcesEmpty, settings: { description, exclude } }),
    ),
  );
}

function getDescription(): HTMLElement {
  return screen.getByRole("textbox", { name: "Search description" });
}

function getExcludeInput(): HTMLElement {
  return screen.getByRole("textbox", { name: "Exclude words" });
}

function getSave(): HTMLElement {
  return screen.getByRole("button", { name: "Save" });
}

function getSettingsSection(): HTMLElement {
  return screen.getByRole("region", { name: "What are you looking for?" });
}

function chipTexts(): string[] {
  const list = within(getSettingsSection()).queryByRole("list");
  if (!list) return [];
  return within(list)
    .getAllByRole("listitem")
    .map((item) => item.textContent?.replace("×", "") ?? "");
}

async function renderLoaded(): Promise<void> {
  renderWithProviders(<InboxPage />);
  await waitFor(() => expect(getDescription()).toBeEnabled());
}

describe("Search settings in the Sources panel", () => {
  it("keeps the form disabled until settings load, then fills it", async () => {
    serveSettings("Senior frontend, React", ["java", "office only"]);
    renderWithProviders(<InboxPage />);

    expect(getDescription()).toBeDisabled();
    expect(getExcludeInput()).toBeDisabled();
    expect(getSave()).toBeDisabled();
    expect(screen.queryByText(HINT)).not.toBeInTheDocument();

    await waitFor(() => expect(getDescription()).toBeEnabled());
    expect(getDescription()).toHaveValue("Senior frontend, React");
    expect(screen.getByText("22/500")).toBeInTheDocument();
    expect(chipTexts()).toEqual(["java", "office only"]);
    expect(getSave()).toBeEnabled();
    expect(screen.queryByText(HINT)).not.toBeInTheDocument();
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
    serveSettings("a".repeat(498), []);
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

  it("adds, dedupes and removes exclude words", async () => {
    const user = userEvent.setup();
    await renderLoaded();

    await user.type(getExcludeInput(), "Java{Enter}php,JAVA{Enter}");
    expect(chipTexts()).toEqual(["Java", "php"]);

    await user.click(screen.getByRole("button", { name: "Remove Java" }));
    expect(chipTexts()).toEqual(["php"]);

    await user.click(getExcludeInput());
    await user.keyboard("{Backspace}");
    expect(chipTexts()).toEqual([]);
  });

  it("blocks the 51st exclude word with a message", async () => {
    serveSettings("Frontend", Array.from({ length: 49 }, (_, i) => `term${i}`));
    const user = userEvent.setup();
    await renderLoaded();
    expect(screen.queryByText("You can add up to 50 exclude words")).not.toBeInTheDocument();

    await user.type(getExcludeInput(), "term49{Enter}");

    expect(chipTexts()).toHaveLength(50);
    expect(getExcludeInput()).toBeDisabled();
    expect(screen.getByText("You can add up to 50 exclude words")).toBeInTheDocument();
  });

  it("saves both fields and shows the server-normalized values", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.patch(SETTINGS_URL, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ description: "Senior React", exclude: ["java", "office only"] });
      }),
    );
    const user = userEvent.setup();
    await renderLoaded();

    await user.type(getDescription(), "  Senior React  ");
    await user.type(getExcludeInput(), "Java{Enter}Office Only{Enter}");
    await user.click(getSave());

    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(bodies).toEqual([
      { description: "  Senior React  ", exclude: ["Java", "Office Only"] },
    ]);
    expect(getDescription()).toHaveValue("Senior React");
    expect(chipTexts()).toEqual(["java", "office only"]);
    expect(screen.getByText("12/500")).toBeInTheDocument();
    await waitFor(() => expect(getSave()).toHaveFocus());
  });

  it("sends a blank description as null and uses the default normalizing handler", async () => {
    serveSettings("Old", ["php"]);
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
    expect(bodies).toEqual([{ description: null, exclude: ["php"] }]);
    expect(getDescription()).toHaveValue("");
    expect(screen.getByText(HINT)).toBeInTheDocument();
  });

  it("adds a typed exclude word that was not confirmed with Enter when saving", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.patch(SETTINGS_URL, async ({ request }) => {
        const body = (await request.json()) as { description: string | null; exclude: string[] };
        bodies.push(body);
        return HttpResponse.json(body);
      }),
    );
    const user = userEvent.setup();
    await renderLoaded();

    await user.type(getExcludeInput(), "ruby");
    await user.click(getSave());

    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(bodies).toEqual([{ description: null, exclude: ["ruby"] }]);
  });

  it("shows a 400 error inline and keeps the drafts", async () => {
    server.use(
      http.patch(SETTINGS_URL, () =>
        HttpResponse.json({ detail: "You can add up to 50 exclude words" }, { status: 400 }),
      ),
    );
    const user = userEvent.setup();
    await renderLoaded();

    await user.type(getDescription(), "Frontend");
    await user.click(getSave());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You can add up to 50 exclude words",
    );
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
        return HttpResponse.json({ description: "Frontend", exclude: [] });
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
