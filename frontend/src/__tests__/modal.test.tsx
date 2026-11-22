import { useEffect, useState } from "react";
import { act, createEvent, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Modal } from "@/shared/ui";

interface HarnessProps {
  isDismissable?: boolean;
  onClose?: () => void;
}

/** An opener button plus a modal with a heading-first button, two fields and a footer. */
function Harness({ isDismissable = true, onClose }: HarnessProps) {
  const [isOpen, setIsOpen] = useState(false);
  const close = () => {
    onClose?.();
    setIsOpen(false);
  };
  return (
    <>
      <button type="button" onClick={() => setIsOpen(true)}>
        Open dialog
      </button>
      {isOpen ? (
        <Modal title="Edit item" onClose={close} isDismissable={isDismissable}>
          <button type="button">Help</button>
          <label>
            Name
            <input />
          </label>
          <label>
            Notes
            <textarea />
          </label>
          <button type="button" onClick={close}>
            Done
          </button>
        </Modal>
      ) : null}
    </>
  );
}

async function openDialog() {
  const user = userEvent.setup();
  render(<Harness />);
  await user.click(screen.getByRole("button", { name: "Open dialog" }));
  return user;
}

describe("Modal", () => {
  it("is a modal dialog named by its title", async () => {
    await openDialog();

    const dialog = screen.getByRole("dialog", { name: "Edit item" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  it("focuses the first form field, not the first button", async () => {
    await openDialog();

    expect(screen.getByRole("textbox", { name: "Name" })).toHaveFocus();
  });

  it("keeps Tab and Shift+Tab inside the dialog", async () => {
    const user = await openDialog();

    screen.getByRole("button", { name: "Done" }).focus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Help" })).toHaveFocus();

    await user.tab({ shift: true });
    expect(screen.getByRole("button", { name: "Done" })).toHaveFocus();
  });

  it("closes on Escape and returns focus to the opener", async () => {
    const user = await openDialog();

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open dialog" })).toHaveFocus();
  });

  it("returns focus to the opener when closed from inside", async () => {
    const user = await openDialog();

    await user.click(screen.getByRole("button", { name: "Done" }));

    expect(screen.getByRole("button", { name: "Open dialog" })).toHaveFocus();
  });

  it("closes on a backdrop click but not on a click inside", async () => {
    const user = await openDialog();

    await user.click(screen.getByRole("textbox", { name: "Notes" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.click(screen.getByTestId("modal-backdrop"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("ignores Escape and backdrop clicks while not dismissable", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<Harness isDismissable={false} onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: "Open dialog" }));

    await user.keyboard("{Escape}");
    await user.click(screen.getByTestId("modal-backdrop"));

    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("Modal focus containment", () => {
  it("keeps focus inside after a press on the backdrop, so Tab stays in the dialog", async () => {
    const user = await openDialog();
    const name = screen.getByRole("textbox", { name: "Name" });

    const backdrop = screen.getByTestId("modal-backdrop");
    const event = createEvent.mouseDown(backdrop);
    fireEvent(backdrop, event);
    expect(event.defaultPrevented).toBe(true);
    await user.pointer({ keys: "[MouseLeft>]", target: backdrop });
    expect(name).toHaveFocus();

    await user.tab();
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });

  it("pulls focus back when something outside gets focus", async () => {
    await openDialog();

    act(() => screen.getByRole("button", { name: "Open dialog", hidden: true }).focus());

    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });
});

describe("Nested modals", () => {
  function Nested({ onDocumentEscape }: { onDocumentEscape: () => void }) {
    const [depth, setDepth] = useState(0);
    useEffect(() => {
      function handle(event: KeyboardEvent): void {
        if (event.key === "Escape") onDocumentEscape();
      }
      document.addEventListener("keydown", handle);
      return () => document.removeEventListener("keydown", handle);
    }, [onDocumentEscape]);
    return (
      <>
        <button type="button" onClick={() => setDepth(1)}>
          Open outer
        </button>
        {depth >= 1 ? (
          <Modal title="Outer" onClose={() => setDepth(0)}>
            <button type="button" onClick={() => setDepth(2)}>
              Open inner
            </button>
            {depth >= 2 ? (
              <Modal title="Inner" onClose={() => setDepth(1)}>
                <input aria-label="Inner field" />
              </Modal>
            ) : null}
          </Modal>
        ) : null}
      </>
    );
  }

  it("Escape closes only the top modal and never reaches document listeners", async () => {
    const onDocumentEscape = vi.fn();
    const user = userEvent.setup();
    render(<Nested onDocumentEscape={onDocumentEscape} />);
    await user.click(screen.getByRole("button", { name: "Open outer" }));
    await user.click(screen.getByRole("button", { name: "Open inner" }));
    expect(screen.getByRole("textbox", { name: "Inner field" })).toHaveFocus();

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog", { name: "Inner" })).not.toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Outer" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open inner" })).toHaveFocus();

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(onDocumentEscape).not.toHaveBeenCalled();
  });
});
