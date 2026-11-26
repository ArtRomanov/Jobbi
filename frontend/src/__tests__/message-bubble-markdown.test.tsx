import { render, screen } from "@testing-library/react";
import { MessageBubble } from "@/features/chat-interface";

function renderAssistant(content: string, isStreaming = false) {
  return render(<MessageBubble role="assistant" content={content} isStreaming={isStreaming} />);
}

describe("MessageBubble Markdown", () => {
  it("renders headings, lists, quotes and emphasis as elements", () => {
    const { container } = renderAssistant(
      [
        "### Summary",
        "",
        "Some **bold** and *italic* and `code`.",
        "",
        "- one",
        "  - nested",
        "- two",
        "",
        "1. first",
        "2. second",
        "",
        "> quoted",
        "",
        "---",
        "",
        "```",
        "const a = 1;",
        "```",
      ].join("\n"),
    );

    expect(screen.getByRole("heading", { name: "Summary" })).toBeInTheDocument();
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByText("italic").tagName).toBe("EM");
    expect(screen.getByText("code").tagName).toBe("CODE");
    expect(container.querySelectorAll("ul")).toHaveLength(2);
    expect(container.querySelector("ol")).toHaveTextContent("firstsecond");
    expect(container.querySelector("blockquote")).toHaveTextContent("quoted");
    expect(container.querySelector("hr")).not.toBeNull();
    expect(container.querySelector("pre code")).toHaveTextContent("const a = 1;");
    expect(container.textContent).not.toContain("###");
    expect(container.textContent).not.toContain("**");
  });

  it("shows raw HTML as text and never injects it", () => {
    const { container } = renderAssistant(
      'Hi <script>alert(1)</script>\n\n<img src="x" onerror="alert(1)">',
    );

    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<script>alert(1)</script>");
    expect(container.textContent).toContain('<img src="x" onerror="alert(1)">');
  });

  it("links only safe URLs, in a new tab", () => {
    const { container } = renderAssistant(
      "[bad](javascript:alert(1)) and [good](https://example.com)",
    );

    const links = container.querySelectorAll("a");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "https://example.com");
    expect(links[0]).toHaveAttribute("target", "_blank");
    expect(links[0]).toHaveAttribute("rel", "noopener noreferrer");
    expect(container.textContent).toContain("[bad](javascript:alert(1))");
  });

  it("keeps user messages as plain text", () => {
    const { container } = render(<MessageBubble role="user" content={"### Not a heading\n**raw**"} />);

    expect(screen.queryByRole("heading")).toBeNull();
    expect(container.querySelector("strong")).toBeNull();
    expect(container.textContent).toContain("### Not a heading\n**raw**");
    expect(container.firstElementChild).toHaveStyle({ whiteSpace: "pre-wrap" });
  });

  it.each(["### Ti", "Some **unterminated", "- item\n- ", "```js\nconst", "[link](https://exa"])(
    "renders partial streaming Markdown %j without error, cursor last",
    (content) => {
      const { container } = renderAssistant(content, true);
      const cursor = container.querySelector('[aria-hidden="true"]');
      expect(cursor).not.toBeNull();
      const all = Array.from(container.querySelectorAll("*"));
      // Nothing but the cursor's own position after it: it is the last leaf.
      const leaves = all.filter((el) => el.children.length === 0);
      expect(leaves[leaves.length - 1]).toBe(cursor);
    },
  );
});
