import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MetricsPage } from "@/pages/metrics/ui/metrics-page";
import { renderWithProviders } from "./utils";
import { mockMetrics } from "./mocks/handlers";
import { server } from "./setup";

vi.mock("@/features/metrics-dashboard", async () => {
  const actual = await vi.importActual<
    typeof import("@/features/metrics-dashboard")
  >("@/features/metrics-dashboard");
  return { ...actual, TrendChart: () => <div data-testid="trend-chart" /> };
});

beforeEach(() => {
  localStorage.setItem("jobbi_token", "test-token");
});

describe("MetricsPage", () => {
  it("renders KPI labels and values", async () => {
    renderWithProviders(<MetricsPage />);

    await waitFor(() => {
      expect(screen.getByText("Total Applications")).toBeInTheDocument();
    });

    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("Response Rate")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("Interviews")).toBeInTheDocument();
    // "4" appears for both the Interviews KPI and the "applied" pipeline count
    expect(screen.getAllByText("4").length).toBeGreaterThanOrEqual(1);
  });

  it("renders all six pipeline statuses", async () => {
    renderWithProviders(<MetricsPage />);

    await waitFor(() => {
      expect(screen.getByText("Researching")).toBeInTheDocument();
    });

    expect(screen.getByText("Applied")).toBeInTheDocument();
    expect(screen.getByText("Interview")).toBeInTheDocument();
    expect(screen.getByText("Offer")).toBeInTheDocument();
    expect(screen.getByText("Rejected")).toBeInTheDocument();
    expect(screen.getByText("Withdrawn")).toBeInTheDocument();
  });

  it("renders date range selector with all four range buttons", async () => {
    renderWithProviders(<MetricsPage />);

    expect(
      screen.getByRole("button", { name: "Last 7 days" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Last 30 days" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Last 90 days" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "All time" }),
    ).toBeInTheDocument();
  });

  it("shows empty state when no applications", async () => {
    server.use(
      http.get("*/api/v1/metrics", () => {
        return HttpResponse.json({
          ...mockMetrics,
          kpis: { ...mockMetrics.kpis, total_applications: 0 },
        });
      }),
    );

    renderWithProviders(<MetricsPage />);

    await waitFor(() => {
      expect(
        screen.getByText(/no applications yet/i),
      ).toBeInTheDocument();
    });
  });
});
