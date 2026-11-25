import { StrictMode, useState } from "react";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLocation } from "react-router-dom";
import { delay, http, HttpResponse } from "msw";
import { ChatPage } from "@/pages/chat/ui/chat-page";
import { mockChangeCards } from "./mocks/handlers";
import { server } from "./setup";
import { renderWithProviders } from "./utils";

const BASE_URL = "http://localhost:8000";
const CARD_TITLE = /^CV text — change \d+$/;
const ACCEPT = /^Accept change \d+$/;
const REJECT = /^Reject change \d+$/;
const OUTDATED = "Outdated — newer messages below";

function renderChatPage(applicationId: string) {
  return renderWithProviders(<ChatPage />, {
    initialEntries: [`/applications/${applicationId}/chat`],
    path: "/applications/:id/chat",
    routes: [{ path: "/dashboard", element: <p>Dashboard</p> }],
  });
}

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
});

describe("ChatPage", () => {
  it("renders chat page with application context in header", async () => {
    // The default handler returns mockApplicationDetail for app-1
    // which has company_name "Acme Corp" and role_title "Senior Engineer"
    renderChatPage("app-1");

    await waitFor(() => {
      expect(screen.getByText(/Acme Corp — Senior Engineer/)).toBeInTheDocument();
    });
  });

  it("renders message history from the server", async () => {
    renderChatPage("app-1");

    await waitFor(() => {
      expect(
        screen.getByText(
          "Help me prepare for my interview at Acme Corp.",
        ),
      ).toBeInTheDocument();
    });

    expect(
      screen.getByText(
        /I'd be happy to help you prepare for your interview/,
      ),
    ).toBeInTheDocument();
  });

  it("shows empty state when there are no messages", async () => {
    // Override the chat history handler to return an empty array
    server.use(
      http.get(`${BASE_URL}/api/v1/applications/:id/chat`, () => {
        return HttpResponse.json([]);
      }),
    );

    renderChatPage("app-1");

    await waitFor(() => {
      expect(
        screen.getByText(/No messages yet/),
      ).toBeInTheDocument();
    });
  });
});

describe("ChatPage draft from router state", () => {
  const DRAFT = "Adapt my CV to this vacancy";

  function StateProbe() {
    const location = useLocation();
    return <output aria-label="router state">{JSON.stringify(location.state)}</output>;
  }

  /** Chat route plus a "Remount" button that re-creates the page like a reload would. */
  function RemountableChat() {
    const [generation, setGeneration] = useState(0);
    return (
      <>
        <ChatPage key={generation} />
        <StateProbe />
        <button type="button" onClick={() => setGeneration((value) => value + 1)}>
          Remount
        </button>
      </>
    );
  }

  function renderWithDraft() {
    return renderWithProviders(<RemountableChat />, {
      initialEntries: [{ pathname: "/applications/app-1/chat", state: { draft: DRAFT } }],
      path: "/applications/:id/chat",
    });
  }

  it("pre-fills the input without sending it", async () => {
    let chatPosts = 0;
    server.use(
      http.post(`${BASE_URL}/api/v1/applications/:id/chat`, () => {
        chatPosts += 1;
        return new HttpResponse(null, { status: 500 });
      }),
    );
    renderWithDraft();

    const input = screen.getByRole("textbox", { name: "Chat message" });
    expect(input).toHaveValue(DRAFT);
    await screen.findByText(/Acme Corp — Senior Engineer/);
    expect(chatPosts).toBe(0);
    expect(screen.queryByText(DRAFT, { selector: "p, div" })).not.toBeInTheDocument();
  });

  it("clears the router state so a reload or remount does not re-fill", async () => {
    const user = userEvent.setup();
    renderWithDraft();
    expect(screen.getByRole("textbox", { name: "Chat message" })).toHaveValue(DRAFT);
    await waitFor(() =>
      expect(screen.getByRole("status", { name: "router state" })).toHaveTextContent("null"),
    );

    await user.click(screen.getByRole("button", { name: "Remount" }));

    expect(screen.getByRole("textbox", { name: "Chat message" })).toHaveValue("");
  });

  it("starts empty without a draft", () => {
    renderChatPage("app-1");

    expect(screen.getByRole("textbox", { name: "Chat message" })).toHaveValue("");
  });
});

describe("ChatPage draft under StrictMode", () => {
  it("pre-fills once and clears the router state despite double effects", async () => {
    function StateProbe() {
      const location = useLocation();
      return <output aria-label="router state">{JSON.stringify(location.state)}</output>;
    }
    renderWithProviders(
      <>
        <ChatPage />
        <StateProbe />
      </>,
      {
        initialEntries: [
          { pathname: "/applications/app-1/chat", state: { draft: "Adapt my CV to this vacancy" } },
        ],
        path: "/applications/:id/chat",
        wrapper: StrictMode,
      },
    );

    expect(screen.getByRole("textbox", { name: "Chat message" })).toHaveValue("Adapt my CV to this vacancy");
    await waitFor(() =>
      expect(screen.getByRole("status", { name: "router state" })).toHaveTextContent("null"),
    );
    await screen.findByText(/Acme Corp — Senior Engineer/);
    expect(screen.getByRole("textbox", { name: "Chat message" })).toHaveValue("Adapt my CV to this vacancy");
  });
});

describe("ChatPage change cards", () => {
  const userMessage = {
    id: "msg-1",
    application_id: "app-1",
    role: "user",
    content: "Improve my CV",
    created_at: "2026-03-01T10:00:00Z",
    cards: [],
  };
  const assistantMessage = {
    id: "msg-2",
    application_id: "app-1",
    role: "assistant",
    content: "Here are two edits.",
    created_at: "2026-03-01T10:01:00Z",
    cards: [mockChangeCards.replace, mockChangeCards.remove],
  };

  function sseBody(frames: string[]): ReadableStream<Uint8Array> {
    const encoder = new TextEncoder();
    return new ReadableStream({
      start(controller) {
        for (const frame of frames) controller.enqueue(encoder.encode(frame));
        controller.close();
      },
    });
  }

  it("renders cards from the history after a reload, in order, still clickable", async () => {
    const user = userEvent.setup();
    server.use(
      http.get(`${BASE_URL}/api/v1/applications/:id/chat`, () =>
        HttpResponse.json([userMessage, assistantMessage]),
      ),
    );
    renderChatPage("app-1");

    await screen.findByText("Here are two edits.");
    const cards = screen.getAllByRole("article", { name: CARD_TITLE });
    expect(cards).toHaveLength(2);
    expect(within(cards[0]!).getByText("Before")).toBeInTheDocument();
    expect(within(cards[1]!).getByText("Removed")).toBeInTheDocument();

    await user.click(within(cards[0]!).getByRole("button", { name: ACCEPT }));

    expect(await within(cards[0]!).findByText("Accepted")).toBeInTheDocument();
    expect(within(cards[1]!).getByRole("button", { name: ACCEPT })).toBeEnabled();
  });

  it("only the newest message's cards can be decided; older ones say outdated", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/applications/:id/chat`, () =>
        HttpResponse.json([
          userMessage,
          {
            ...assistantMessage,
            cards: [
              mockChangeCards.replace,
              { ...mockChangeCards.remove, state: "accepted" },
            ],
          },
          { ...userMessage, id: "msg-3", content: "And the summary?" },
          // The newest reply has no cards: every card above is outdated
          { ...assistantMessage, id: "msg-4", content: "Looks fine.", cards: [] },
        ]),
      ),
    );
    renderChatPage("app-1");

    await screen.findByText("Looks fine.");
    const [pending, accepted] = screen.getAllByRole("article", { name: CARD_TITLE });
    expect(within(pending!).getByText(OUTDATED)).toBeInTheDocument();
    expect(within(pending!).queryByRole("button")).not.toBeInTheDocument();
    // Decided cards keep their own label, without the outdated note
    expect(within(accepted!).getByText("Accepted")).toBeInTheDocument();
    expect(within(accepted!).queryByText(OUTDATED)).not.toBeInTheDocument();
  });

  it("makes the cards outdated as soon as a new message is sent, while it streams", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/applications/:id/chat`, () =>
        HttpResponse.json([userMessage, assistantMessage]),
      ),
      // The reply never arrives: the stream is still running
      http.post(`${BASE_URL}/api/v1/applications/:id/chat`, async () => {
        await delay("infinite");
        return new HttpResponse(null);
      }),
    );
    const user = userEvent.setup();
    renderChatPage("app-1");
    await screen.findByText("Here are two edits.");
    expect(screen.getAllByRole("button", { name: ACCEPT })).toHaveLength(2);

    await user.type(screen.getByRole("textbox", { name: "Chat message" }), "More");
    await user.keyboard("{Enter}");

    expect(await screen.findAllByText(OUTDATED)).toHaveLength(2);
    expect(screen.queryByRole("button", { name: ACCEPT })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: REJECT })).not.toBeInTheDocument();
  });

  /**
   * GET /chat answers `[]` until the message is sent, then `afterSend`;
   * POST /chat streams `frames`. Returns the number of GET calls so far.
   */
  function mockStream(frames: string[], afterSend: unknown[]): () => number {
    let posted = false;
    let getCalls = 0;
    server.use(
      http.get(`${BASE_URL}/api/v1/applications/:id/chat`, () => {
        getCalls += 1;
        return HttpResponse.json(posted ? afterSend : []);
      }),
      http.post(`${BASE_URL}/api/v1/applications/:id/chat`, () => {
        posted = true;
        return new HttpResponse(sseBody(frames), {
          headers: { "Content-Type": "text/event-stream" },
        });
      }),
    );
    return () => getCalls;
  }

  async function send(text: string): Promise<void> {
    const user = userEvent.setup();
    await screen.findByText(/No messages yet/);
    await user.type(screen.getByRole("textbox", { name: "Chat message" }), text);
    await user.keyboard("{Enter}");
  }

  const cardsFrame = (cards: unknown[]): string =>
    `event: cards\ndata: ${JSON.stringify(cards)}\n\n`;
  // Same framing as the backend: JSON payloads on one `data:` line
  const tokenFrame = (text: string): string =>
    `event: token\ndata: ${JSON.stringify({ text })}\n\n`;
  const DONE = `event: done\ndata: ${JSON.stringify({ status: "complete" })}\n\n`;

  it("attaches cards from the SSE stream to the streamed reply", async () => {
    const getCalls = mockStream(
      [
        tokenFrame("Added "),
        tokenFrame("it."),
        cardsFrame([mockChangeCards.insert]),
        DONE,
      ],
      [
        { ...userMessage, content: "Add GraphQL" },
        { ...assistantMessage, content: "Added it.", cards: [mockChangeCards.insert] },
      ],
    );
    renderChatPage("app-1");
    await send("Add GraphQL");

    const card = await screen.findByRole("article", { name: CARD_TITLE });
    expect(within(card).getByText("Added after: ## Skills")).toBeInTheDocument();
    expect(screen.getByText("Added it.")).toBeInTheDocument();

    // The history reload after `done` keeps the same card element (same message id)
    await waitFor(() => expect(getCalls()).toBe(2));
    expect(screen.getByRole("article", { name: CARD_TITLE })).toBe(card);

    await userEvent.setup().click(within(card).getByRole("button", { name: REJECT }));
    expect(await screen.findByText("Rejected")).toBeInTheDocument();
    expect(screen.getAllByRole("article", { name: CARD_TITLE })).toHaveLength(1);
  });

  it("replaces the streamed text with the `reply` event before the cards", async () => {
    let posted = false;
    server.use(
      http.get(`${BASE_URL}/api/v1/applications/:id/chat`, async () => {
        if (!posted) return HttpResponse.json([]);
        // The reload never lands: what shows comes from the stream alone
        await new Promise<never>(() => undefined);
        return HttpResponse.json([]);
      }),
      http.post(`${BASE_URL}/api/v1/applications/:id/chat`, () => {
        posted = true;
        return new HttpResponse(
          sseBody([
            tokenFrame("1. Add REST API"),
            `event: reply\ndata: ${JSON.stringify({
              text: "1. Add REST API (not proposed — see below)\n\nLeft out one change.",
            })}\n\n`,
            cardsFrame([mockChangeCards.insert]),
            DONE,
          ]),
          { headers: { "Content-Type": "text/event-stream" } },
        );
      }),
    );
    renderChatPage("app-1");
    await send("Tailor my CV");

    expect(
      await screen.findByText(/1\. Add REST API \(not proposed — see below\)/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Left out one change\./)).toBeInTheDocument();
    expect(screen.getByRole("article", { name: CARD_TITLE })).toBeInTheDocument();
  });

  it("keeps a card decided while the history reload was in flight", async () => {
    let releaseReload: () => void = () => undefined;
    const reloadGate = new Promise<void>((resolve) => {
      releaseReload = resolve;
    });
    let posted = false;
    let getCalls = 0;
    server.use(
      http.get(`${BASE_URL}/api/v1/applications/:id/chat`, async () => {
        getCalls += 1;
        if (!posted) return HttpResponse.json([]);
        // The reload read the card before the Accept landed: still pending
        await reloadGate;
        return HttpResponse.json([
          { ...userMessage, content: "Add GraphQL" },
          { ...assistantMessage, content: "Added it (saved).", cards: [mockChangeCards.insert] },
        ]);
      }),
      http.post(`${BASE_URL}/api/v1/applications/:id/chat`, () => {
        posted = true;
        return new HttpResponse(
          sseBody([tokenFrame("Added it."), cardsFrame([mockChangeCards.insert]), DONE]),
          { headers: { "Content-Type": "text/event-stream" } },
        );
      }),
    );
    renderChatPage("app-1");
    await send("Add GraphQL");

    const card = await screen.findByRole("article", { name: CARD_TITLE });
    await waitFor(() => expect(getCalls).toBe(2));
    await userEvent.setup().click(within(card).getByRole("button", { name: ACCEPT }));
    expect(await within(card).findByText("Accepted")).toBeInTheDocument();

    releaseReload();

    // The reload has landed (the saved reply text replaced the streamed one)
    expect(await screen.findByText("Added it (saved).")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("article", { name: CARD_TITLE })).toHaveAttribute(
        "data-state",
        "accepted",
      ),
    );
    expect(screen.queryByRole("button", { name: ACCEPT })).not.toBeInTheDocument();
  });

  it("shows a cards-only reply without an empty assistant bubble", async () => {
    const getCalls = mockStream(
      [cardsFrame([mockChangeCards.remove]), DONE],
      [
        { ...userMessage, content: "Drop my contacts" },
        { ...assistantMessage, content: "", cards: [mockChangeCards.remove] },
      ],
    );
    const { container } = renderChatPage("app-1");
    await send("Drop my contacts");

    const card = await screen.findByRole("article", { name: CARD_TITLE });
    expect(within(card).getByText("Removed")).toBeInTheDocument();
    await waitFor(() => expect(getCalls()).toBe(2));
    expect(screen.getByRole("article", { name: CARD_TITLE })).toBe(card);
    expect(container.querySelectorAll('[data-message-role="assistant"]')).toHaveLength(0);
  });

  it("shows the decoded text of token frames, not their JSON", async () => {
    mockStream(
      [tokenFrame('Line one\nwith "quotes"'), cardsFrame([]), DONE],
      [],
    );
    const { container } = renderChatPage("app-1");
    await screen.findByText(/No messages yet/);
    // Hold the reload after `done`, so the streamed reply stays on screen
    server.use(
      http.get(`${BASE_URL}/api/v1/applications/:id/chat`, async () => {
        await delay("infinite");
        return HttpResponse.json([]);
      }),
    );
    await send("Hi");

    await waitFor(() =>
      expect(
        container.querySelector('[data-message-role="assistant"]'),
      ).toHaveTextContent('Line one with "quotes"'),
    );
    expect(screen.queryByText(/\{"text"/)).not.toBeInTheDocument();
  });

  it("shows the decoded detail of an error frame", async () => {
    mockStream(
      [`event: error\ndata: ${JSON.stringify({ detail: "Model unavailable" })}\n\n`],
      [],
    );
    renderChatPage("app-1");
    await send("Hi");

    expect(await screen.findByText("Model unavailable")).toBeInTheDocument();
  });

  const errorFrame = (detail: string): string =>
    `event: error\ndata: ${JSON.stringify({ detail })}\n\n`;

  it("reloads the history when the stream fails after tokens, so a saved reply shows", async () => {
    const getCalls = mockStream(
      [tokenFrame("Here is "), tokenFrame("the answer."), errorFrame("Something went wrong.")],
      [
        { ...userMessage, content: "Help" },
        { ...assistantMessage, content: "Here is the answer.", cards: [mockChangeCards.insert] },
      ],
    );
    renderChatPage("app-1");
    await send("Help");

    expect(await screen.findByText("Something went wrong.")).toBeInTheDocument();
    await waitFor(() => expect(getCalls()).toBe(2));
    expect(await screen.findByText("Here is the answer.")).toBeInTheDocument();
    expect(screen.getByRole("article", { name: CARD_TITLE })).toBeInTheDocument();
  });

  it("does not reload the history when the stream fails before any token", async () => {
    const getCalls = mockStream([errorFrame("Something went wrong.")], []);
    renderChatPage("app-1");
    await send("Help");

    expect(await screen.findByText("Something went wrong.")).toBeInTheDocument();
    expect(getCalls()).toBe(1);
  });

  it("ignores an empty cards event", async () => {
    const getCalls = mockStream(
      [tokenFrame("No edits needed."), cardsFrame([]), DONE],
      [
        { ...userMessage, content: "Is my CV fine?" },
        { ...assistantMessage, content: "No edits needed.", cards: [] },
      ],
    );
    const { container } = renderChatPage("app-1");
    await send("Is my CV fine?");

    await waitFor(() => expect(getCalls()).toBe(2));
    expect(await screen.findByText("No edits needed.")).toBeInTheDocument();
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
    expect(container.querySelectorAll('[data-message-role="assistant"]')).toHaveLength(1);
  });
});
