import { useState } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ChangeCard } from "@/entities/chat";
import { parseCardsEvent } from "@/entities/chat";
import { CvChangeCard, mergeCardStates } from "@/features/chat-interface";
import { buildCardDiff } from "@/features/chat-interface/lib/build-diff-rows";
import { getInsertLabel } from "@/features/chat-interface/lib/card-labels";
import { ToastProvider } from "@/shared/ui";
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
const CARD_TITLE = /^CV text — change \d+$/;
const ACCEPT = /^Accept change \d+$/;
const REJECT = /^Reject change \d+$/;

function card(overrides: Partial<ChangeCard> = {}): ChangeCard {
  return { ...mockChangeCards.replace, ...overrides };
}

/** Holds the cards in state like the chat page does, so decisions re-render. */
function Harness({
  initial,
  outdated,
}: {
  initial: ChangeCard[];
  outdated?: boolean;
}) {
  const [cards, setCards] = useState(initial);
  const onCardUpdated = (updated: ChangeCard): void =>
    setCards((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
  return (
    <>
      {cards.map((c, index) => (
        <CvChangeCard
          key={c.id}
          applicationId="app-1"
          card={c}
          number={index + 1}
          outdated={outdated}
          onCardUpdated={onCardUpdated}
        />
      ))}
    </>
  );
}

function renderOutdated(...cards: ChangeCard[]) {
  return render(
    <ToastProvider>
      <Harness initial={cards} outdated />
    </ToastProvider>,
  );
}

function renderCards(...cards: ChangeCard[]) {
  // The card toasts "Change applied to your CV" after Accept
  return render(
    <ToastProvider>
      <Harness initial={cards} />
    </ToastProvider>,
  );
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

    const article = screen.getByRole("article", { name: CARD_TITLE });
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
    expect(screen.getByRole("button", { name: ACCEPT })).toBeEnabled();
    expect(screen.getByRole("button", { name: REJECT })).toBeEnabled();
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
    expect(screen.getByRole("button", { name: ACCEPT })).toBeDisabled();
    expect(screen.getByRole("button", { name: REJECT })).toBeEnabled();
  });
});

describe("CvChangeCard of an older reply (outdated)", () => {
  const OUTDATED = "Outdated — newer messages below";

  it("pending: no buttons, a muted outdated note", () => {
    renderOutdated(card());
    expect(screen.getByText(OUTDATED)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it.each([
    ["accepted", "Accepted"],
    ["rejected", "Rejected"],
    ["stale", "Stale"],
  ] as const)("%s: keeps its badge, no buttons, no outdated note", (state, badge) => {
    renderOutdated(card({ state }));
    expect(screen.getByText(badge)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByText(OUTDATED)).not.toBeInTheDocument();
  });
});

describe("CvChangeCard decisions", () => {
  it("accepts: the card becomes Accepted and the buttons go", async () => {
    const user = userEvent.setup();
    renderCards(card());

    await user.click(screen.getByRole("button", { name: ACCEPT }));

    expect(await screen.findByText("Accepted")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: ACCEPT })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: REJECT })).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("Change applied to your CV")).toBeInTheDocument();
  });

  it("rejects: the card becomes Rejected", async () => {
    const user = userEvent.setup();
    renderCards(card());

    await user.click(screen.getByRole("button", { name: REJECT }));

    expect(await screen.findByText("Rejected")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    // Reject saves nothing, so no toast
    expect(screen.queryByText("Change applied to your CV")).not.toBeInTheDocument();
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

    await user.click(screen.getByRole("button", { name: ACCEPT }));

    expect(screen.getByRole("button", { name: ACCEPT })).toBeDisabled();
    expect(screen.getByRole("button", { name: REJECT })).toBeDisabled();
    release();
    expect(await screen.findByText("Accepted")).toBeInTheDocument();
  });

  it("CARD_STALE: shows the stale text, marks the card Stale, Reject still works", async () => {
    const user = userEvent.setup();
    failAccept(409, "CARD_STALE");
    renderCards(card());

    await user.click(screen.getByRole("button", { name: ACCEPT }));

    expect(await screen.findByRole("alert")).toHaveTextContent(STALE_TEXT);
    expect(screen.getByText("Stale")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: ACCEPT })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: REJECT }));

    expect(await screen.findByText("Rejected")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it.each([
    [409, "PASSAGE_NOT_UNIQUE", NOT_UNIQUE_TEXT],
    [422, "TOO_LONG", TOO_LONG_TEXT],
    [409, "CV_BUSY", GENERIC_TEXT],
    [404, "Not found", GENERIC_TEXT],
    [500, "CARD_STALE", GENERIC_TEXT],
  ])("%i %s: shows the error and the card stays Pending", async (status, detail, text) => {
    const user = userEvent.setup();
    failAccept(status, detail);
    renderCards(card());

    await user.click(screen.getByRole("button", { name: ACCEPT }));

    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(screen.getByRole("article")).toHaveAttribute("data-state", "pending");
    expect(screen.getByRole("button", { name: ACCEPT })).toBeEnabled();
    expect(screen.getByRole("button", { name: REJECT })).toBeEnabled();
  });

  it("shows the generic error on a network failure", async () => {
    const user = userEvent.setup();
    server.use(http.post(`${CARDS_URL}/accept`, () => HttpResponse.error()));
    renderCards(card());

    await user.click(screen.getByRole("button", { name: ACCEPT }));

    expect(await screen.findByRole("alert")).toHaveTextContent(GENERIC_TEXT);
  });

  it("CARD_OUTDATED (a newer message from another tab): toasts, card stays pending", async () => {
    const user = userEvent.setup();
    failAccept(409, "CARD_OUTDATED");
    renderCards(card());

    await user.click(screen.getByRole("button", { name: ACCEPT }));

    expect(
      await screen.findByText(
        "This change is outdated: only the latest reply's changes can be applied.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("article")).toHaveAttribute("data-state", "pending");
    expect(screen.getByRole("button", { name: ACCEPT })).toBeEnabled();
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

    await user.click(screen.getByRole("button", { name: ACCEPT }));

    expect(await screen.findByText("Rejected")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("rejects a stale card (Accept stays disabled)", async () => {
    const user = userEvent.setup();
    renderCards(card({ state: "stale", decided_at: null }));

    await user.click(screen.getByRole("button", { name: REJECT }));

    expect(await screen.findByText("Rejected")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    // Reject saves nothing, so no toast
    expect(screen.queryByText("Change applied to your CV")).not.toBeInTheDocument();
  });

  it("decides each card on its own", async () => {
    const user = userEvent.setup();
    renderCards(card(), card(mockChangeCards.insert));

    const [first, second] = screen.getAllByRole("article", { name: CARD_TITLE });
    await user.click(within(first!).getByRole("button", { name: REJECT }));

    expect(await within(first!).findByText("Rejected")).toBeInTheDocument();
    expect(within(second!).getByRole("button", { name: ACCEPT })).toBeEnabled();

    await user.click(within(second!).getByRole("button", { name: ACCEPT }));
    await waitFor(() =>
      expect(within(second!).getByText("Accepted")).toBeInTheDocument(),
    );
    expect(within(first!).getByText("Rejected")).toBeInTheDocument();
  });
});

describe("CvChangeCard accessibility", () => {
  it("numbers cards within a message: title, article name and button names", () => {
    renderCards(card(), card(mockChangeCards.insert));

    const first = screen.getByRole("article", { name: "CV text — change 1" });
    const second = screen.getByRole("article", { name: "CV text — change 2" });
    expect(
      within(first).getByRole("button", { name: "Accept change 1" }),
    ).toHaveTextContent("Accept");
    expect(
      within(first).getByRole("button", { name: "Reject change 1" }),
    ).toHaveTextContent("Reject");
    expect(
      within(second).getByRole("button", { name: "Accept change 2" }),
    ).toBeInTheDocument();
    expect(
      within(second).getByRole("button", { name: "Reject change 2" }),
    ).toBeInTheDocument();
  });

  it("moves focus to the card title after Accept resolves", async () => {
    const user = userEvent.setup();
    renderCards(card());

    await user.click(screen.getByRole("button", { name: "Accept change 1" }));

    expect(await screen.findByText("Accepted")).toBeInTheDocument();
    const title = screen.getByText("CV text — change 1");
    await waitFor(() => expect(title).toHaveFocus());
    expect(title).toHaveAttribute("tabindex", "-1");
  });

  it("moves focus to the card title after Reject resolves", async () => {
    const user = userEvent.setup();
    renderCards(card());

    await user.click(screen.getByRole("button", { name: "Reject change 1" }));

    expect(await screen.findByText("Rejected")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText("CV text — change 1")).toHaveFocus(),
    );
  });

  it("announces the new state through a status region that is always mounted", async () => {
    const user = userEvent.setup();
    renderCards(card());

    const status = screen.getByRole("status");
    expect(status).toBeEmptyDOMElement();

    await user.click(screen.getByRole("button", { name: "Accept change 1" }));

    await waitFor(() => expect(status).toHaveTextContent("Accepted"));
    expect(screen.getByRole("status")).toBe(status);
  });
});

describe("CvChangeCard warning (backlog #27)", () => {
  const WARNING = mockChangeCards.warned.warning;

  it("shows no warning when the card has none", () => {
    renderCards(card());
    expect(screen.queryByText(/Check before accepting/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: ACCEPT })).not.toHaveAttribute("aria-describedby");
  });

  it("shows the warning, describes Accept with it and keeps Accept enabled", () => {
    renderCards(mockChangeCards.warned);
    const article = screen.getByRole("article", { name: CARD_TITLE });
    expect(within(article).getByText(WARNING, { exact: false })).toHaveTextContent(
      `Check before accepting: ${WARNING}`,
    );
    const accept = screen.getByRole("button", { name: ACCEPT });
    expect(accept).toBeEnabled();
    expect(accept).toHaveAccessibleDescription(`Check before accepting: ${WARNING}`);
  });

  it("accepts a warned card: the warning stays, the card becomes Accepted", async () => {
    const user = userEvent.setup();
    renderCards(mockChangeCards.warned);

    await user.click(screen.getByRole("button", { name: ACCEPT }));

    expect(await screen.findByText("Accepted")).toBeInTheDocument();
    expect(screen.getByText(WARNING, { exact: false })).toBeInTheDocument();
  });

  it("parseCardsEvent keeps the warning and reads a missing one as null", () => {
    const { warning: _missing, ...withoutWarning } = mockChangeCards.replace;
    const data = JSON.stringify([mockChangeCards.warned, withoutWarning, { ...withoutWarning, id: "x", warning: 5 }]);
    expect(parseCardsEvent(data)).toEqual([mockChangeCards.warned, mockChangeCards.replace]);
  });
});

describe("card helpers", () => {
  it("mergeCardStates keeps a local decision over a pending server copy", () => {
    const message = {
      id: "msg-2",
      application_id: "app-1",
      role: "assistant",
      content: "Edits",
      created_at: "2026-03-01T10:01:00Z",
    };
    const local = [
      { ...message, cards: [card({ state: "accepted" }), card({ id: "b", state: "pending" })] },
    ];
    const fresh = [
      { ...message, cards: [card({ state: "pending" }), card({ id: "b", state: "rejected" })] },
    ];

    const merged = mergeCardStates(local, fresh);

    expect(merged[0]!.cards.map((c) => c.state)).toEqual(["accepted", "rejected"]);
    // Nothing to merge: the fresh history is used as is
    expect(mergeCardStates([], fresh)).toBe(fresh);
  });

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
