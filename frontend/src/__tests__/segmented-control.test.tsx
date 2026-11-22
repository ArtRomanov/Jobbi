import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SegmentedControl } from "@/shared/ui";

const OPTIONS = [
  { value: "new", label: "New" },
  { value: "seen", label: "Seen" },
  { value: "all", label: "All" },
] as const;

type Value = (typeof OPTIONS)[number]["value"];

function Harness({ onChange }: { onChange?: (value: Value) => void }) {
  const [value, setValue] = useState<Value>("seen");
  return (
    <>
      <button type="button">Before</button>
      <SegmentedControl
        label="Show"
        options={OPTIONS}
        value={value}
        onChange={(next) => {
          setValue(next);
          onChange?.(next);
        }}
      />
      <button type="button">After</button>
    </>
  );
}

function checked(): string | null {
  return screen
    .getAllByRole("radio")
    .find((radio) => radio.getAttribute("aria-checked") === "true")?.textContent ?? null;
}

describe("SegmentedControl", () => {
  it("is a labelled radio group with one checked option", () => {
    render(<Harness />);

    expect(screen.getByRole("radiogroup", { name: "Show" })).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    expect(checked()).toBe("Seen");
  });

  it("puts only the checked option in the tab order", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: "Before" }));
    await user.tab();
    expect(screen.getByRole("radio", { name: "Seen" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "After" })).toHaveFocus();
  });

  it("moves focus and selection with arrow keys (wrapping), Home and End", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "Before" }));
    await user.tab();

    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "All" })).toHaveFocus();
    expect(checked()).toBe("All");

    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "New" })).toHaveFocus();
    expect(checked()).toBe("New");

    await user.keyboard("{ArrowLeft}");
    expect(checked()).toBe("All");
    await user.keyboard("{ArrowUp}");
    expect(checked()).toBe("Seen");
    await user.keyboard("{ArrowDown}");
    expect(checked()).toBe("All");

    await user.keyboard("{Home}");
    expect(screen.getByRole("radio", { name: "New" })).toHaveFocus();
    expect(checked()).toBe("New");
    await user.keyboard("{End}");
    expect(screen.getByRole("radio", { name: "All" })).toHaveFocus();
    expect(checked()).toBe("All");

    expect(onChange.mock.calls.map(([value]) => value)).toEqual([
      "all",
      "new",
      "all",
      "seen",
      "all",
      "new",
      "all",
    ]);
  });

  it("selects on click and does not report a click on the checked option", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness onChange={onChange} />);

    await user.click(screen.getByRole("radio", { name: "Seen" }));
    expect(onChange).not.toHaveBeenCalled();

    await user.click(screen.getByRole("radio", { name: "New" }));
    expect(onChange).toHaveBeenCalledWith("new");
    expect(checked()).toBe("New");
  });
});
