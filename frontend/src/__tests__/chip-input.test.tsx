import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { ChipInput } from "@/shared/ui";

interface HarnessProps {
  initial?: readonly string[];
  maxItems?: number;
  maxLength?: number;
  disabled?: boolean;
  onChange?: (values: readonly string[]) => void;
}

/** Controlled wrapper: ChipInput keeps no chip state of its own. */
function Harness({ initial = [], onChange, ...props }: HarnessProps) {
  const [values, setValues] = useState<readonly string[]>(initial);
  return (
    <ChipInput
      label="Exclude words"
      hint="Press Enter or comma to add."
      maxItemsMessage="Limit reached"
      values={values}
      onChange={(next) => {
        setValues(next);
        onChange?.(next);
      }}
      {...props}
    />
  );
}

function getInput(): HTMLElement {
  return screen.getByRole("textbox", { name: "Exclude words" });
}

function chipTexts(): string[] {
  const list = screen.queryByRole("list");
  if (!list) return [];
  return within(list)
    .getAllByRole("listitem")
    .map((item) => item.textContent?.replace("×", "") ?? "");
}

describe("ChipInput", () => {
  it("labels the input and links the hint", () => {
    render(<Harness />);

    expect(getInput()).toHaveAccessibleDescription("Press Enter or comma to add.");
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("adds a trimmed term on Enter and clears the input", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(getInput(), "  java  {Enter}");

    expect(chipTexts()).toEqual(["java"]);
    expect(getInput()).toHaveValue("");
    expect(getInput()).toHaveFocus();
  });

  it("adds on comma, including several terms pasted at once", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(getInput(), "php,");
    expect(chipTexts()).toEqual(["php"]);

    await user.click(getInput());
    await user.paste("office only, ruby ,go");
    expect(chipTexts()).toEqual(["php", "office only", "ruby"]);
    // The part after the last comma stays as the draft
    expect(getInput()).toHaveValue("go");
  });

  it("ignores empty terms and case-insensitive duplicates", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness initial={["Java"]} onChange={onChange} />);

    await user.type(getInput(), "   {Enter}");
    await user.type(getInput(), ",");
    await user.type(getInput(), "JAVA{Enter}");

    expect(chipTexts()).toEqual(["Java"]);
    expect(onChange).not.toHaveBeenCalled();
    expect(getInput()).toHaveValue("");
  });

  it("adds the typed term when the input loses focus", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(getInput(), "kotlin");
    await user.tab();

    expect(chipTexts()).toEqual(["kotlin"]);
  });

  it("removes a chip with its Remove button and focuses the input", async () => {
    const user = userEvent.setup();
    render(<Harness initial={["java", "php"]} />);

    await user.click(screen.getByRole("button", { name: "Remove java" }));

    expect(chipTexts()).toEqual(["php"]);
    expect(getInput()).toHaveFocus();
  });

  it("removes the last chip on Backspace in an empty input only", async () => {
    const user = userEvent.setup();
    render(<Harness initial={["java", "php"]} />);

    await user.type(getInput(), "x{Backspace}");
    expect(chipTexts()).toEqual(["java", "php"]);

    await user.keyboard("{Backspace}");
    expect(chipTexts()).toEqual(["java"]);
    await user.keyboard("{Backspace}{Backspace}");
    expect(chipTexts()).toEqual([]);
  });

  it("cuts a term to maxLength", async () => {
    const user = userEvent.setup();
    render(<Harness maxLength={5} />);

    await user.type(getInput(), "abcdefgh");
    expect(getInput()).toHaveValue("abcde");
    await user.keyboard("{Enter}");

    expect(chipTexts()).toEqual(["abcde"]);
  });

  it("disables the input and shows the message at maxItems", async () => {
    const user = userEvent.setup();
    render(<Harness initial={["a"]} maxItems={2} />);
    expect(screen.queryByText("Limit reached")).not.toBeInTheDocument();

    await user.type(getInput(), "b{Enter}");

    expect(chipTexts()).toEqual(["a", "b"]);
    expect(getInput()).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("Limit reached");
    expect(getInput()).toHaveAccessibleDescription("Press Enter or comma to add. Limit reached");
    // Focus stays inside the control instead of falling to <body>
    expect(screen.getByRole("button", { name: "Remove b" })).toHaveFocus();

    await user.click(screen.getByRole("button", { name: "Remove a" }));
    expect(getInput()).toBeEnabled();
    expect(screen.queryByText("Limit reached")).not.toBeInTheDocument();
  });

  it("stops adding pasted terms at maxItems", async () => {
    const user = userEvent.setup();
    render(<Harness maxItems={2} />);

    await user.click(getInput());
    await user.paste("a, b, c,");

    expect(chipTexts()).toEqual(["a", "b"]);
  });

  it("disables input and Remove buttons when disabled", () => {
    render(<Harness initial={["java"]} disabled />);

    expect(getInput()).toBeDisabled();
    expect(screen.getByRole("button", { name: "Remove java" })).toBeDisabled();
  });
});
