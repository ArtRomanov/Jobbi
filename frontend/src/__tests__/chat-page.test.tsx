import { StrictMode, useState } from "react";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLocation } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { ChatPage } from "@/pages/chat/ui/chat-page";
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
