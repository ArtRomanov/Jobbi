import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { ChatPage } from "@/pages/chat/ui/chat-page";
import { ToastProvider } from "@/shared/ui";
import { server } from "./setup";

const BASE_URL = "http://localhost:8000";

function renderChatPage(applicationId: string) {
  return render(
    <MemoryRouter
      initialEntries={[`/applications/${applicationId}/chat`]}
    >
      <ToastProvider>
        <Routes>
          <Route
            path="/applications/:id/chat"
            element={<ChatPage />}
          />
          <Route path="/dashboard" element={<p>Dashboard</p>} />
        </Routes>
      </ToastProvider>
    </MemoryRouter>,
  );
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
