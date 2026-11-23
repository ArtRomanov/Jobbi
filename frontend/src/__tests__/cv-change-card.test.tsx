import { useState } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ChangeCard } from "@/entities/chat";
import { parseCardsEvent } from "@/entities/chat";
import { CvChangeCard } from "@/features/chat-interface";
import { buildCardDiff } from "@/features/chat-interface/lib/build-diff-rows";
import { getInsertLabel } from "@/features/chat-interface/lib/card-labels";
import { mockChangeCards } from "./mocks/handlers";
import { server } from "./setup";

const BASE_URL = "http://localhost:8000";
const CARDS_URL = `${BASE_URL}/api/v1/applications/:id/chat/cards/:cardId`;

const STALE_TEXT =
  "This part of the CV has changed since the suggestion. Ask the assistant again.";
const NOT_UNIQUE_TEXT =
  "This text appears more than once in the CV. Ask the assistant to quote a longer part.";
const TOO_LONG_TEXT =
  "This change would make the CV longer than 20 000 characters.";
const GENERIC_TEXT = "Could not apply this change. Please try again.";

function card(overrides: Partial<ChangeCard> = {}): ChangeCard {
  return { ...mockChangeCards.replace, ...overrides };
}

/** Holds the cards in state like the chat page does, so decisions re-render. */
function Harness({ initial }: { initial: ChangeCard[] }) {
  const [cards, setCards] = useState(initial);
  const onCardUpdated = (updated: ChangeCard): void =>
    setCards((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
  return (
    <>
      {cards.map((c) => (
        <CvChangeCard
          key={c.id}
          applicationId="app-1"
          card={c}
          onCardUpdated={onCardUpdated}
        />
      ))}
    </>
  );
}

function renderCards(...cards: ChangeCard[]) {
  return render(<Harness initial={cards} />);
}

function failAccept(status: number, detail: string): void {
  server.use(
    http.post(`${CARDS_URL}/accept`, () =>
      HttpResponse.json({ detail }, { status }),
    ),
  );
}

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
});

describe("CvChangeCard rendering", () => {
  it("shows a replace card with before/after and −/+ diff markers", () => {
    const { container } = renderCards(card());

    const article = screen.getByRole("article", { name: "CV text" });
    expect(within(article).getByText("Before")).toBeInTheDocument();
    expect(within(article).getByText("After")).toBeInTheDocument();

    const removed = container.querySelectorAll('[data-diff="removed"]');
    const added = container.querySelectorAll('[data-diff="added"]');
    expect(removed).toHaveLength(1);
    expect(added).toHaveLength(1);
    expect(removed[0]).toHaveTextContent("−Removed line: Experienced software engineer.");
    expect(added[0]).toHaveTextContent(
      "+Added line: Senior software engineer with 8 years in React.",
    );
    expect(removed[0]?.tagName).toBe("DEL");
    expect(added[0]?.tagName).toBe("INS");
    // The unchanged heading shows in both columns, unmarked
    expect(container.querySelectorAll('[data-diff="same"]')).toHaveLength(2);
  });

  it("shows an insert card with only the after text and its position label", () => {
    const { container } = renderCards(card(mockChangeCards.insert));

    expect(screen.getByText("Added after: ## Skills")).toBeInTheDocument();
    expect(screen.queryByText("Before")).not.toBeInTheDocument();
    expect(container.querySelectorAll('[data-diff="removed"]')).toHaveLength(0);
    expect(container.querySelector('[data-diff="added"]')).toHaveTextContent(
      "GraphQL, Node.js",
    );
  });

  it("labels insertions at the start, at the end and after a long line", () => {
    expect(getInsertLabel({ position: "start", anchor_text: null })).toBe(
      "Added at the start",
    );
    expect(getInsertLabel({ position: "end", anchor_text: null })).toBe(
      "Added at the end",
    );
    expect(
      getInsertLabel({
        position: "after_line",
        anchor_text:
          "Led a team of five engineers building the payments platform\nsecond line",
      }),
    ).toBe("Added after: Led a team of five engineers building…");
  });

  it("shows a remove card with only the before text, labelled Removed", () => {
    const { container } = renderCards(card(mockChangeCards.remove));

    expect(screen.getByText("Removed")).toBeInTheDocument();
    expect(screen.queryByText("After")).not.toBeInTheDocument();
    expect(container.querySelectorAll('[data-diff="added"]')).toHaveLength(0);
    expect(container.querySelector('[data-diff="removed"]')).toHaveTextContent(
      "test@example.com",
    );
  });

  it("shows Accept and Reject while pending", () => {
    renderCards(card());
    expect(screen.getByRole("button", { name: "Accept" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled();
  });

  it("shows Accepted without buttons", () => {
    renderCards(card({ state: "accepted" }));
    expect(screen.getByText("Accepted")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows Rejected without buttons, struck through", () => {
    renderCards(card({ state: "rejected" }));
    expect(screen.getByText("Rejected")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByRole("article")).toHaveAttribute("data-state", "rejected");
  });

  it("shows Stale with Accept disabled and Reject enabled", () => {
    renderCards(card({ state: "stale" }));
    expect(screen.getByText("Stale")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled();
  });
});

describe("CvChangeCard decisions", () => {
  it("accepts: the card becomes Accepted and the buttons go", async () => {
    const user = userEvent.setup();
    renderCards(card());

    await user.click(screen.getByRole("button", { name: "Accept" }));

    expect(await screen.findByText("Accepted")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("rejects: the card becomes Rejected", async () => {
    const user = userEvent.setup();
    renderCards(card());

    await user.click(screen.getByRole("button", { name: "Reject" }));

    expect(await screen.findByText("Rejected")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("disables both buttons while the request runs", async () => {
    const user = userEvent.setup();
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.post(`${CARDS_URL}/accept`, async () => {
        await gate;
        return HttpResponse.json({ ...card(), state: "accepted" });
      }),
    );
    renderCards(card());

    await user.click(screen.getByRole("button", { name: "Accept" }));

    expect(screen.getByRole("button", { name: "Accept" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
    release();
    expect(await screen.findByText("Accepted")).toBeInTheDocument();
  });

  it("CARD_STALE: shows the stale text, marks the card Stale, Reject still works", async () => {
    const user = userEvent.setup();
    failAccept(409, "CARD_STALE");
    renderCards(card());

    await user.click(screen.getByRole("button", { name: "Accept" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(STALE_TEXT);
    expect(screen.getByText("Stale")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Reject" }));

    expect(await screen.findByText("Rejected")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it.each([
    [409, "PASSAGE_NOT_UNIQUE", NOT_UNIQUE_TEXT],
    [422, "TOO_LONG", TOO_LONG_TEXT],
    [404, "Not found", GENERIC_TEXT],
    [500, "CARD_STALE", GENERIC_TEXT],
  ])("%i %s: shows the error and the card stays Pending", async (status, detail, text) => {
    const user = userEvent.setup();
    failAccept(status, detail);
    renderCards(card());

    await user.click(screen.getByRole("button", { name: "Accept" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(screen.getByRole("article")).toHaveAttribute("data-state", "pending");
    expect(screen.getByRole("button", { name: "Accept" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled();
  });

  it("shows the generic error on a network failure", async () => {
    const user = userEvent.setup();
    server.use(http.post(`${CARDS_URL}/accept`, () => HttpResponse.error()));
    renderCards(card());

    await user.click(screen.getByRole("button", { name: "Accept" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(GENERIC_TEXT);
  });

  it("CARD_DECIDED: refreshes the card from the history without an error", async () => {
    const user = userEvent.setup();
    failAccept(409, "CARD_DECIDED");
    server.use(
      http.get(`${BASE_URL}/api/v1/applications/:id/chat`, () =>
        HttpResponse.json([
          {
            id: "msg-2",
            application_id: "app-1",
            role: "assistant",
            content: "Here is a change.",
            created_at: "2026-03-01T10:01:00Z",
            cards: [{ ...card(), state: "rejected" }],
          },
        ]),
      ),
    );
    renderCards(card());

    await user.click(screen.getByRole("button", { name: "Accept" }));

    expect(await screen.findByText("Rejected")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("rejects a stale card (Accept stays disabled)", async () => {
    const user = userEvent.setup();
    renderCards(card({ state: "stale", decided_at: null }));

    await user.click(screen.getByRole("button", { name: "Reject" }));

    expect(await screen.findByText("Rejected")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("decides each card on its own", async () => {
    const user = userEvent.setup();
    renderCards(card(), card(mockChangeCards.insert));

    const [first, second] = screen.getAllByRole("article", { name: "CV text" });
    await user.click(within(first!).getByRole("button", { name: "Reject" }));

    expect(await within(first!).findByText("Rejected")).toBeInTheDocument();
    expect(within(second!).getByRole("button", { name: "Accept" })).toBeEnabled();

    await user.click(within(second!).getByRole("button", { name: "Accept" }));
    await waitFor(() =>
      expect(within(second!).getByText("Accepted")).toBeInTheDocument(),
    );
    expect(within(first!).getByText("Rejected")).toBeInTheDocument();
  });
});

describe("card helpers", () => {
  it("buildCardDiff keeps unchanged lines in both columns", () => {
    const diff = buildCardDiff("a\nb\nc", "a\nB\nc");
    expect(diff.before.map((r) => `${r.kind}:${r.text}`)).toEqual([
      "same:a",
      "removed:b",
      "same:c",
    ]);
    expect(diff.after.map((r) => `${r.kind}:${r.text}`)).toEqual([
      "same:a",
      "added:B",
      "same:c",
    ]);
  });

  it("parseCardsEvent keeps valid cards and drops junk", () => {
    const { message_id: _dropped, ...withoutMessageId } = mockChangeCards.replace;
    const data = JSON.stringify([
      mockChangeCards.replace,
      { id: 1 },
      null,
      withoutMessageId,
    ]);
    expect(parseCardsEvent(data)).toEqual([mockChangeCards.replace]);
    expect(parseCardsEvent("not json")).toEqual([]);
    expect(parseCardsEvent("{}")).toEqual([]);
  });
});
