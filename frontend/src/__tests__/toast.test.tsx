import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useToast } from "@/shared/ui";
import type { ToastOptions, ToastType } from "@/shared/ui";
import { renderWithProviders } from "./utils";

function Trigger({ type = "success", options }: { type?: ToastType; options?: ToastOptions }) {
  const { showToast } = useToast();
  return (
    <button type="button" onClick={() => showToast("Hello", type, options)}>
      Show
    </button>
  );
}

describe("Toast", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("keeps the old two-argument call: message for 3 s in a live region", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"], shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<Trigger />);

    await user.click(screen.getByRole("button", { name: "Show" }));
    const message = screen.getByText("Hello");
    expect(message.closest("[aria-live='polite']")).not.toBeNull();

    await act(() => vi.advanceTimersByTimeAsync(2900));
    expect(screen.getByText("Hello")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(200));
    expect(screen.queryByText("Hello")).not.toBeInTheDocument();
  });

  it("runs the action, closes the toast and honours a custom duration", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"], shouldAdvanceTime: true });
    const onUndo = vi.fn();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(
      <Trigger type="info" options={{ durationMs: 5000, action: { label: "Undo", onClick: onUndo } }} />,
    );

    await user.click(screen.getByRole("button", { name: "Show" }));
    await act(() => vi.advanceTimersByTimeAsync(4000));
    const undo = screen.getByRole("button", { name: "Undo" });
    expect(undo.closest("[aria-live='polite']")).not.toBeNull();

    await user.click(undo);
    expect(onUndo).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Hello")).not.toBeInTheDocument();
  });

  it("removes the action when the duration ends", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"], shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(
      <Trigger options={{ durationMs: 5000, action: { label: "Undo", onClick: vi.fn() } }} />,
    );

    await user.click(screen.getByRole("button", { name: "Show" }));
    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
  });

  it("renders a link that navigates and closes the toast", async () => {
    const user = userEvent.setup();
    const { router } = renderWithProviders(
      <Trigger options={{ link: { label: "Open it", to: "/target" } }} />,
    );

    await user.click(screen.getByRole("button", { name: "Show" }));
    const link = screen.getByRole("link", { name: "Open it" });
    expect(link).toHaveAttribute("href", "/target");

    await user.click(link);
    expect(router.state.location.pathname).toBe("/target");
    expect(screen.queryByText("Hello")).not.toBeInTheDocument();
  });

  it("pauses while focused and closes after the remaining time once focus leaves", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"], shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(
      <Trigger type="info" options={{ durationMs: 5000, action: { label: "Undo", onClick: vi.fn() } }} />,
    );

    await user.click(screen.getByRole("button", { name: "Show" }));
    await act(() => vi.advanceTimersByTimeAsync(4000));
    const undo = screen.getByRole("button", { name: "Undo" });
    act(() => undo.focus());

    await act(() => vi.advanceTimersByTimeAsync(6000));
    expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();

    act(() => undo.blur());
    await act(() => vi.advanceTimersByTimeAsync(800));
    expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(400));
    expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
  });

  it("pauses while hovered", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"], shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<Trigger options={{ durationMs: 5000 }} />);

    await user.click(screen.getByRole("button", { name: "Show" }));
    await user.hover(screen.getByText("Hello"));
    await act(() => vi.advanceTimersByTimeAsync(8000));
    expect(screen.getByText("Hello")).toBeInTheDocument();

    await user.unhover(screen.getByText("Hello"));
    await act(() => vi.advanceTimersByTimeAsync(5100));
    expect(screen.queryByText("Hello")).not.toBeInTheDocument();
  });

  it("puts error toasts in an alert region and others in a polite one", async () => {
    renderWithProviders(
      <>
        <Trigger type="error" />
        <Trigger type="success" />
      </>,
    );
    const user = userEvent.setup();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    const [showError, showSuccess] = screen.getAllByRole("button", { name: "Show" });
    await user.click(showError!);
    await user.click(showSuccess!);

    const messages = screen.getAllByText("Hello");
    expect(screen.getByRole("alert")).toContainElement(messages[1] ?? null);
    expect(messages[0]?.closest("[aria-live='polite']")).not.toBeNull();
  });

  it("runs onTimeout only when the toast closes by its own timer", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"], shouldAdvanceTime: true });
    const onTimeout = vi.fn();
    const onUndo = vi.fn();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(
      <Trigger
        type="info"
        options={{ durationMs: 5000, action: { label: "Undo", onClick: onUndo }, onTimeout }}
      />,
    );

    // Closed by its action: no onTimeout
    await user.click(screen.getByRole("button", { name: "Show" }));
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await act(() => vi.advanceTimersByTimeAsync(6000));
    expect(onTimeout).not.toHaveBeenCalled();

    // Closed by its timer: onTimeout once
    await user.click(screen.getByRole("button", { name: "Show" }));
    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(screen.queryByText("Hello")).not.toBeInTheDocument();
    expect(onTimeout).toHaveBeenCalledTimes(1);
    await act(() => vi.advanceTimersByTimeAsync(6000));
    expect(onTimeout).toHaveBeenCalledTimes(1);
  });
});
