import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { InboxPage } from "@/pages/inbox";
import { colors } from "@/shared/ui";
import { renderWithProviders } from "./utils";
import {
  mockVacancy,
  mockVacancyPageEmpty,
  mockVacancySource,
  mockVacancySourcesEmpty,
} from "./mocks/handlers";
import { server } from "./setup";

const VACANCIES_URL = "*/api/v1/vacancies";
const SOURCES_URL = "*/api/v1/vacancy-sources";

/** WCAG 2.x relative luminance of a #rrggbb color. */
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((start) => {
    const channel = parseInt(hex.slice(start, start + 2), 16) / 255;
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG 2.x contrast ratio, 1–21. */
function contrastRatio(foreground: string, background: string): number {
  const [light, dark] = [luminance(foreground), luminance(background)].sort((a, b) => b - a) as [
    number,
    number,
  ];
  return (light + 0.05) / (dark + 0.05);
}

function serveTwoCards(): void {
  const longText = "x".repeat(400);
  server.use(
    http.get(VACANCIES_URL, () =>
      HttpResponse.json({
        ...mockVacancyPageEmpty,
        total: 2,
        items: [
          { ...mockVacancy, text: longText },
          {
            ...mockVacancy,
            id: "vac-2",
            title: "Frontend Engineer",
            company: "Beta",
            state: "seen",
            fit: "low",
            text: longText,
          },
        ],
      }),
    ),
  );
}

describe("contrast helper", () => {
  it("matches known WCAG reference ratios", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrastRatio("#ffffff", "#ffffff")).toBeCloseTo(1, 5);
    // Order of the arguments does not matter
    expect(contrastRatio("#767676", "#ffffff")).toBeCloseTo(contrastRatio("#ffffff", "#767676"), 5);
    expect(contrastRatio("#767676", "#ffffff")).toBeGreaterThanOrEqual(4.5);
  });
});

describe("theme text contrast (WCAG 1.4.3, 4.5:1)", () => {
  const pairs: [string, string, string][] = [
    ...Object.entries(colors.badge).map(
      ([tone, { bg, text }]): [string, string, string] => [`badge ${tone}`, text, bg],
    ),
    ["error text on card", colors.error, colors.bgCard],
    ["muted text on card", colors.textMuted, colors.bgCard],
    ["muted text on page", colors.textMuted, colors.bgPage],
    ["secondary text on the danger tint (unavailable source)", colors.textSecondary, colors.badge.danger.bg],
    ["primary text on card (links, selected segment)", colors.primary, colors.bgCard],
    ["white on primary button", "#ffffff", colors.primary],
    ["white on success toast", "#ffffff", colors.success],
    ["white on error toast", "#ffffff", colors.errorBg],
    ["white on info toast", "#ffffff", colors.textPrimary],
  ];

  it.each(pairs)("%s", (_name, foreground, background) => {
    expect(contrastRatio(foreground, background)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("Inbox accessibility", () => {
  it("gives every card action a distinct, label-first accessible name", async () => {
    serveTwoCards();
    renderWithProviders(<InboxPage />);

    const list = await screen.findByRole("list", { name: "Vacancies" });
    const [first, second] = within(list).getAllByRole("article");

    expect(
      within(first!).getByRole("button", { name: "Open source for Senior React Developer at Acme" }),
    ).toBeInTheDocument();
    expect(
      within(first!).getByRole("button", { name: "Add to tracker: Senior React Developer at Acme" }),
    ).toBeInTheDocument();
    expect(
      within(first!).getByRole("button", { name: "Dismiss Senior React Developer at Acme" }),
    ).toBeInTheDocument();
    expect(
      within(first!).getByRole("button", { name: "Show more about Senior React Developer at Acme" }),
    ).toBeInTheDocument();
    expect(
      within(second!).getByRole("button", { name: "Dismiss Frontend Engineer at Beta" }),
    ).toBeInTheDocument();

    // No two buttons on the page share a name
    const names = screen.getAllByRole("button").map((button) => button.getAttribute("aria-label") ?? button.textContent);
    const cardNames = names.filter((name) => / at (Acme|Beta)$/.test(name ?? ""));
    expect(cardNames).toHaveLength(8);
    expect(new Set(cardNames).size).toBe(cardNames.length);
  });

  it("states the fit in text, not only by badge color", async () => {
    serveTwoCards();
    renderWithProviders(<InboxPage />);

    const list = await screen.findByRole("list", { name: "Vacancies" });
    const [first, second] = within(list).getAllByRole("article");
    expect(within(first!).getByText("High").textContent).toBe("Fit: High");
    expect(within(second!).getByText("Low").textContent).toBe("Fit: Low");
    // The New marker is text, too
    expect(within(first!).getByText("New")).toBeInTheDocument();
  });

  it("has one h1 and an h2 above the card h3s and the Sources section", async () => {
    serveTwoCards();
    renderWithProviders(<InboxPage />);
    await screen.findByRole("list", { name: "Vacancies" });

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    const headings = screen.getAllByRole("heading");
    const levels = headings.map((heading) => Number(heading.tagName.slice(1)));
    // Never skips a level going down
    levels.forEach((level, index) => {
      if (index > 0) expect(level - levels[index - 1]!).toBeLessThanOrEqual(1);
    });
    expect(screen.getByRole("heading", { level: 2, name: "Vacancies" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Sources" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Vacancies" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Sources" })).toBeInTheDocument();
  });

  it("keeps the browser focus ring on the Sources text fields", async () => {
    renderWithProviders(<InboxPage />);

    const addInput = await screen.findByRole("textbox", { name: "Add a channel, job board or page" });
    const excludeInput = screen.getByRole("textbox", { name: "Exclude words" });
    const description = screen.getByRole("textbox", { name: "Search description" });
    for (const field of [addInput, excludeInput, description]) {
      expect(field.style.outline).toBe("");
      expect(field.style.outlineStyle).toBe("");
    }
  });

  it("keeps the meta line of an unavailable source readable on its tinted row", async () => {
    server.use(
      http.get(SOURCES_URL, () =>
        HttpResponse.json({
          ...mockVacancySourcesEmpty,
          sources: [{ ...mockVacancySource, id: "gone", unavailable: true, last_error: "Gone" }],
        }),
      ),
    );
    renderWithProviders(<InboxPage />);

    const list = await screen.findByRole("list", { name: "Watched sources" });
    const meta = within(list).getByText(/^Telegram/);
    expect(meta).toHaveStyle({ color: colors.textSecondary });
  });
});
