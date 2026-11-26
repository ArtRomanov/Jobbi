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

interface ServedSettings {
  keywords?: string[];
  keyword_filter?: boolean;
  filtered_last_24h?: number;
}

function serveSettings(description: string | null, extra: ServedSettings = {}): void {
  const { filtered_last_24h = 0, ...settings } = extra;
  server.use(
    http.get(SOURCES_URL, () =>
      HttpResponse.json({
        ...mockVacancySourcesEmpty,
        settings: { ...mockVacancySourcesEmpty.settings, description, ...settings },
        status: { ...mockVacancySourcesEmpty.status, filtered_last_24h },
      }),
    ),
  );
}

function getKeywordsInput(): HTMLElement {
  return screen.getByRole("textbox", { name: "Keywords" });
}

function getKeywordChips(): string[] {
  const list = screen.queryByRole("list", { name: "Keywords" });
  if (list === null) return [];
  return within(list)
    .queryAllByRole("listitem")
    .map((item) => item.textContent?.replace("×", "").trim() ?? "");
}

function getFilterSwitch(): HTMLElement {
  return screen.getByRole("switch", { name: "Only send posts with these words to the AI" });
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
    // Loaded but untouched: focusable, yet nothing to save
    expect(getSave()).toBeEnabled();
    expect(getSave()).toHaveAttribute("aria-disabled", "true");
    expect(screen.queryByText(HINT)).not.toBeInTheDocument();
  });

  it("has description, keywords and the switch (no exclude words) and sends all three", async () => {
    serveSettings("Frontend", { keywords: ["react"], keyword_filter: true });
    const bodies: unknown[] = [];
    server.use(
      http.patch(SETTINGS_URL, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({
          description: "Frontend React",
          keywords: ["react"],
          keyword_filter: true,
        });
      }),
    );
    const user = userEvent.setup();
    await renderLoaded();

    const section = getSettingsSection();
    expect(within(section).getAllByRole("textbox")).toEqual([getDescription(), getKeywordsInput()]);
    expect(getFilterSwitch()).toBeChecked();
    expect(screen.queryByRole("textbox", { name: "Exclude words" })).not.toBeInTheDocument();
    expect(screen.queryByText(/exclude/i)).not.toBeInTheDocument();

    await user.type(getDescription(), " React");
    await user.click(getSave());

    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(bodies).toEqual([
      { description: "Frontend React", keywords: ["react"], keyword_filter: true },
    ]);
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

  it("saves the raw description and shows the server-normalized value", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.patch(SETTINGS_URL, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ description: "Senior React", keywords: [], keyword_filter: true });
      }),
    );
    const user = userEvent.setup();
    await renderLoaded();

    await user.type(getDescription(), "  Senior React  ");
    await user.click(getSave());

    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(bodies).toEqual([{ description: "  Senior React  ", keywords: [], keyword_filter: true }]);
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
    expect(bodies).toEqual([{ description: null, keywords: [], keyword_filter: true }]);
    expect(getDescription()).toHaveValue("");
    expect(screen.getByText(HINT)).toBeInTheDocument();
  });

  it.each([
    // Python keeps U+FEFF: a real description, not a cleared one
    { typed: "\ufeff", sent: "\ufeff" },
    // Python strips U+0085 (JS trim does not): blank → null
    { typed: "\u0085 ", sent: null },
  ])("decides 'blank' like the server's Python strip ($typed.length chars → $sent)", async ({ typed, sent }) => {
    serveSettings("Senior React");
    const bodies: unknown[] = [];
    server.events.on("request:start", async ({ request }) => {
      if (request.method === "PATCH") bodies.push(await request.clone().json());
    });
    const user = userEvent.setup();
    await renderLoaded();

    await user.clear(getDescription());
    await user.click(getDescription());
    await user.paste(typed);
    await user.click(getSave());
    await waitFor(() => expect(bodies).toHaveLength(1));
    server.events.removeAllListeners();

    expect(bodies).toEqual([{ description: sent, keywords: [], keyword_filter: true }]);
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
        return HttpResponse.json({ description: "Frontend", keywords: [], keyword_filter: true });
      }),
    );
    const user = userEvent.setup();
    await renderLoaded();

    await user.type(getDescription(), "Frontend");
    await user.click(getSave());

    expect(getSave()).toHaveAttribute("aria-busy", "true");
    // Stays focusable while loading so focus is not dropped
    expect(getSave()).toHaveAttribute("aria-disabled", "true");
    expect(getSave()).toHaveFocus();
    release();
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(getSave()).not.toHaveAttribute("aria-busy");
    // The drafts now match what was saved
    expect(getSave()).toHaveAttribute("aria-disabled", "true");
  });

  describe("Save is active only with changes", () => {
    it("is off after load, on after an edit and off again after reverting it", async () => {
      serveSettings("Frontend", { keywords: ["react"], keyword_filter: true });
      const user = userEvent.setup();
      await renderLoaded();

      expect(getSave()).toHaveAttribute("aria-disabled", "true");
      await user.type(getDescription(), "!");
      expect(getSave()).not.toHaveAttribute("aria-disabled");
      await user.type(getDescription(), "{Backspace}");
      expect(getSave()).toHaveAttribute("aria-disabled", "true");

      await user.click(getFilterSwitch());
      expect(getSave()).not.toHaveAttribute("aria-disabled");
      await user.click(getFilterSwitch());
      expect(getSave()).toHaveAttribute("aria-disabled", "true");

      await user.type(getKeywordsInput(), "vue{Enter}");
      expect(getSave()).not.toHaveAttribute("aria-disabled");
      await user.click(screen.getByRole("button", { name: "Remove vue" }));
      expect(getSave()).toHaveAttribute("aria-disabled", "true");
    });

    it("is off again after a successful save and keeps focus", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      await user.type(getDescription(), "Frontend");
      expect(getSave()).not.toHaveAttribute("aria-disabled");
      await user.click(getSave());

      expect(await screen.findByText("Saved")).toBeInTheDocument();
      expect(getSave()).toHaveAttribute("aria-disabled", "true");
      expect(getSave()).toHaveFocus();
    });

    it("ignores a keyword re-typed in another case and spaces-only description edits", async () => {
      serveSettings("Frontend", { keywords: ["react"] });
      const user = userEvent.setup();
      await renderLoaded();

      await user.click(screen.getByRole("button", { name: "Remove react" }));
      expect(getSave()).not.toHaveAttribute("aria-disabled");
      await user.type(getKeywordsInput(), "  React {Enter}");
      expect(getKeywordChips()).toEqual(["React"]);
      expect(getSave()).toHaveAttribute("aria-disabled", "true");

      await user.type(getDescription(), "   ");
      expect(getSave()).toHaveAttribute("aria-disabled", "true");
    });

    it("a description of only spaces is no change when none is saved", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      await user.type(getDescription(), "   ");
      expect(getSave()).toHaveAttribute("aria-disabled", "true");
    });

    it("sends nothing when the aria-disabled Save is pressed", async () => {
      let patches = 0;
      server.use(
        http.patch(SETTINGS_URL, () => {
          patches += 1;
          return HttpResponse.json(mockVacancySourcesEmpty.settings);
        }),
      );
      const user = userEvent.setup();
      await renderLoaded();

      await user.click(getSave());
      getSave().focus();
      await user.keyboard("{Enter}");

      expect(screen.queryByText("Saved")).not.toBeInTheDocument();
      expect(patches).toBe(0);
    });
  });

  describe("keywords and the keyword filter", () => {
    it("starts from the saved keywords, switch state and 24 h counter", async () => {
      serveSettings("Frontend", {
        keywords: ["react", "фронт"],
        keyword_filter: false,
        filtered_last_24h: 17,
      });
      await renderLoaded();

      expect(getKeywordChips()).toEqual(["react", "фронт"]);
      expect(getFilterSwitch()).not.toBeChecked();
      expect(
        screen.getByText("Skipped by the filter in the last 24 hours: 17"),
      ).toBeInTheDocument();
    });

    it("shows a zero counter and links the hints to the fields", async () => {
      await renderLoaded();

      expect(screen.getByText("Skipped by the filter in the last 24 hours: 0")).toBeInTheDocument();
      expect(getKeywordsInput()).toHaveAccessibleDescription(
        /"фронт" finds "фронтенд".*"front end" also finds "front-end"/,
      );
      expect(getFilterSwitch()).toHaveAccessibleDescription(/deleted/);
      expect(getFilterSwitch()).toBeChecked();
    });

    it("adds keywords with Enter and a comma, and removes them", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      await user.type(getKeywordsInput(), "React{Enter}");
      await user.type(getKeywordsInput(), "фронт,front end,");
      expect(getKeywordChips()).toEqual(["React", "фронт", "front end"]);
      // Enter in the chip input never submits the form
      expect(screen.queryByText("Saved")).not.toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Remove фронт" }));
      expect(getKeywordChips()).toEqual(["React", "front end"]);
      expect(getKeywordsInput()).toHaveFocus();
    });

    it("ignores case-insensitive duplicates and cuts keywords to 64 characters", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      await user.type(getKeywordsInput(), "react,REACT,");
      await user.click(getKeywordsInput());
      await user.paste(`${"k".repeat(70)},`);

      expect(getKeywordChips()).toEqual(["react", "k".repeat(64)]);
    });

    it("disables the input at 50 keywords and says why", async () => {
      serveSettings(null, { keywords: Array.from({ length: 50 }, (_, index) => `kw${index}`) });
      await renderLoaded();

      expect(getKeywordsInput()).toBeDisabled();
      expect(screen.getByText("You can add up to 50 keywords")).toBeInTheDocument();
    });

    it("toggles the switch and sends description, keywords and keyword_filter in one PATCH", async () => {
      serveSettings("Frontend", { keywords: ["vue"], keyword_filter: true });
      const bodies: unknown[] = [];
      server.events.on("request:start", async ({ request }) => {
        if (request.method === "PATCH") bodies.push(await request.clone().json());
      });
      const user = userEvent.setup();
      await renderLoaded();

      await user.click(getFilterSwitch());
      expect(getFilterSwitch()).not.toBeChecked();
      await user.type(getKeywordsInput(), "  Front   End {Enter}");
      await user.click(getSave());

      expect(await screen.findByText("Saved")).toBeInTheDocument();
      server.events.removeAllListeners();
      expect(bodies).toEqual([
        { description: "Frontend", keywords: ["vue", "Front   End"], keyword_filter: false },
      ]);
      expect(getFilterSwitch()).not.toBeChecked();
    });

    it("shows the server-normalized keywords after save", async () => {
      server.use(
        http.patch(SETTINGS_URL, () =>
          HttpResponse.json({
            description: null,
            keywords: ["react", "front end"],
            keyword_filter: true,
          }),
        ),
      );
      const user = userEvent.setup();
      await renderLoaded();

      await user.type(getKeywordsInput(), "React,Front  End,REACTJS,");
      expect(getKeywordChips()).toEqual(["React", "Front  End", "REACTJS"]);
      await user.click(getSave());

      expect(await screen.findByText("Saved")).toBeInTheDocument();
      expect(getKeywordChips()).toEqual(["react", "front end"]);
      expect(getFilterSwitch()).toBeChecked();
    });

    it("shows the server's 400 message and keeps the keyword drafts", async () => {
      server.use(
        http.patch(SETTINGS_URL, () =>
          HttpResponse.json({ detail: "Keywords must be 1–64 characters" }, { status: 400 }),
        ),
      );
      const user = userEvent.setup();
      await renderLoaded();

      await user.type(getKeywordsInput(), "react{Enter}");
      await user.click(getSave());

      expect(await screen.findByRole("alert")).toHaveTextContent("Keywords must be 1–64 characters");
      expect(getKeywordChips()).toEqual(["react"]);
      expect(screen.queryByText("Saved")).not.toBeInTheDocument();

      await user.click(getFilterSwitch());
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });
});
