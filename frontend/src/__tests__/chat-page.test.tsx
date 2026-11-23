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
    const cards = screen.getAllByRole("article", { name: "CV text" });
    expect(cards).toHaveLength(2);
    expect(within(cards[0]!).getByText("Before")).toBeInTheDocument();
    expect(within(cards[1]!).getByText("Removed")).toBeInTheDocument();

    await user.click(within(cards[0]!).getByRole("button", { name: "Accept" }));

    expect(await within(cards[0]!).findByText("Accepted")).toBeInTheDocument();
    expect(within(cards[1]!).getByRole("button", { name: "Accept" })).toBeEnabled();
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

    const card = await screen.findByRole("article", { name: "CV text" });
    expect(within(card).getByText("Added after: ## Skills")).toBeInTheDocument();
    expect(screen.getByText("Added it.")).toBeInTheDocument();

    // The history reload after `done` keeps the same card element (same message id)
    await waitFor(() => expect(getCalls()).toBe(2));
    expect(screen.getByRole("article", { name: "CV text" })).toBe(card);

    await userEvent.setup().click(within(card).getByRole("button", { name: "Reject" }));
    expect(await screen.findByText("Rejected")).toBeInTheDocument();
    expect(screen.getAllByRole("article", { name: "CV text" })).toHaveLength(1);
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

    const card = await screen.findByRole("article", { name: "CV text" });
    expect(within(card).getByText("Removed")).toBeInTheDocument();
    await waitFor(() => expect(getCalls()).toBe(2));
    expect(screen.getByRole("article", { name: "CV text" })).toBe(card);
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
