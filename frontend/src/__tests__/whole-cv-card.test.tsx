import { useState } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ChangeCard } from "@/entities/chat";
import { parseCardsEvent } from "@/entities/chat";
import { CvChangeCard } from "@/features/chat-interface";
import { buildSectionDiff } from "@/features/chat-interface/lib/build-section-diff";
import { ToastProvider } from "@/shared/ui";
import { mockChangeCards } from "./mocks/handlers";

const WHOLE = mockChangeCards.replaceAll;

function Harness({ initial }: { initial: ChangeCard }) {
  const [card, setCard] = useState<ChangeCard>(initial);
  return (
    <CvChangeCard
      applicationId="app-1"
      card={card}
      number={1}
      onCardUpdated={setCard}
    />
  );
}

function renderCard(card: ChangeCard = WHOLE) {
  return render(
    <ToastProvider>
      <Harness initial={card} />
    </ToastProvider>,
  );
}

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
});

describe("buildSectionDiff", () => {
  it("splits on ## headings and sorts sections into changed, added, removed and unchanged", () => {
    const diff = buildSectionDiff(WHOLE.before_text, WHOLE.after_text);

    expect(diff.map((s) => [s.title, s.kind])).toEqual([
      ["Header", "unchanged"],
      ["Summary", "changed"],
      ["Skills", "unchanged"],
      ["Languages", "added"],
      ["Hobbies", "removed"],
    ]);
  });

  it("gives a changed section a line diff of its own text", () => {
    const summary = buildSectionDiff(WHOLE.before_text, WHOLE.after_text).find(
      (s) => s.title === "Summary",
    );

    expect(summary?.rows).toEqual([
      { kind: "same", text: "## Summary" },
      { kind: "removed", text: "Experienced engineer." },
      { kind: "added", text: "Senior engineer." },
    ]);
  });

  it("matches sections by heading, ignoring case, and ignores blank-line-only changes", () => {
    const diff = buildSectionDiff(
      "## Skills\n- React\n",
      "## SKILLS\n- React\n\n",
    );
    expect(diff.map((s) => s.kind)).toEqual(["changed"]);

    const same = buildSectionDiff("## Skills\n- React\n", "## Skills\n- React\n\n\n");
    expect(same.map((s) => s.kind)).toEqual(["unchanged"]);
  });

  it("treats a plain-text CV as one header section that the new CV changes", () => {
    const diff = buildSectionDiff(
      "Jane Doe\nEngineer",
      "# Jane Doe\nEngineer\n\n## Skills\n- React",
    );
    expect(diff.map((s) => [s.title, s.kind])).toEqual([
      ["Header", "changed"],
      ["Skills", "added"],
    ]);
  });
});

describe("buildSectionDiff: section order", () => {
  const BEFORE = "# Ann\n\n## Experience\n- A\n\n## Education\n- B\n";
  const SWAPPED = "# Ann\n\n## Education\n- B\n\n## Experience\n- A\n";

  it("marks a section that only moved as moved, not unchanged", () => {
    expect(buildSectionDiff(BEFORE, SWAPPED).map((s) => [s.title, s.kind])).toEqual([
      ["Header", "unchanged"],
      ["Education", "unchanged"],
      ["Experience", "moved"],
    ]);
  });

  it("shows a reorder-only card as a change, never as no change", () => {
    renderCard({ ...WHOLE, before_text: BEFORE, after_text: SWAPPED });
    expect(screen.queryByText("No changes to the CV text.")).not.toBeInTheDocument();
    expect(screen.getByText(/Experience — moved/)).toBeInTheDocument();
  });

  it("reads a heading with a long run of spaces in linear time", () => {
    const heading = `## a${" ".repeat(20_000)}x`;
    const start = performance.now();
    buildSectionDiff(heading, heading);
    expect(performance.now() - start).toBeLessThan(100);
  });
});

describe("whole-CV card", () => {
  it("parses from the SSE cards event", () => {
    expect(parseCardsEvent(JSON.stringify([WHOLE]))).toHaveLength(1);
  });

  it("is titled as the whole CV and shows one block per changed, added and removed section", () => {
    const { container } = renderCard();

    const article = screen.getByRole("article", { name: "Whole CV — change 1" });
    expect(within(article).getByText("Summary — changed")).toBeInTheDocument();
    expect(within(article).getByText("Languages — added")).toBeInTheDocument();
    expect(within(article).getByText("Hobbies — removed")).toBeInTheDocument();
    expect(container.querySelector('[data-diff="added"]')).toBeInTheDocument();
    expect(container.querySelector('[data-diff="removed"]')).toBeInTheDocument();
  });

  it("collapses the unchanged sections", async () => {
    const user = userEvent.setup();
    renderCard();

    const summary = screen.getByText("Unchanged sections (2): Header, Skills");
    const details = summary.closest("details");
    expect(details).not.toHaveAttribute("open");

    await user.click(summary);
    expect(details).toHaveAttribute("open");
  });

  it("accepts and rejects like any card", async () => {
    const user = userEvent.setup();
    renderCard();

    await user.click(screen.getByRole("button", { name: "Accept change 1" }));

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(/accepted/i),
    );
  });

  it("says when the new CV is the same as the old one", () => {
    renderCard({ ...WHOLE, after_text: WHOLE.before_text });
    expect(screen.getByText("No changes to the CV text.")).toBeInTheDocument();
  });
});
