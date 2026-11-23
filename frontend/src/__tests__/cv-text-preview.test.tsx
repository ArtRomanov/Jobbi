import { render, screen } from "@testing-library/react";
import { CvTextPreview } from "@/entities/cv";

describe("CvTextPreview", () => {
  it("renders headings, emphasis and lists as elements", () => {
    render(
      <CvTextPreview
        content={"# Иван Петров\n## Опыт\n**Bold** and *italic*\n\n- one\n- two\n\n2. second\n3. third"}
      />,
    );

    expect(screen.getByRole("heading", { level: 2, name: "Иван Петров" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Опыт" })).toBeInTheDocument();
    expect(screen.getByText("Bold").tagName).toBe("STRONG");
    expect(screen.getByText("italic").tagName).toBe("EM");

    const lists = screen.getAllByRole("list");
    expect(lists[0]?.tagName).toBe("UL");
    expect(lists[1]?.tagName).toBe("OL");
    expect(lists[1]).toHaveAttribute("start", "2");
    expect(screen.getAllByRole("listitem")).toHaveLength(4);
  });

  it("renders safe links that open in a new tab without opener", () => {
    render(<CvTextPreview content={"[Site](https://jane.dev) jane@example.com"} />);

    const site = screen.getByRole("link", { name: "Site (opens in new tab)" });
    expect(site).toHaveAttribute("href", "https://jane.dev");
    expect(site).toHaveAttribute("target", "_blank");
    expect(site).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByRole("link", { name: "jane@example.com (opens in new tab)" })).toHaveAttribute(
      "href",
      "mailto:jane@example.com",
    );
  });

  it("tells screen readers a link opens a new tab, without changing the visible text", () => {
    render(<CvTextPreview content={"[Site](https://jane.dev)"} />);

    const site = screen.getByRole("link", { name: "Site (opens in new tab)" });
    expect(screen.getByText("(opens in new tab)", { exact: false })).toHaveStyle({
      position: "absolute",
      width: "1px",
    });
    expect(site.firstChild?.textContent).toBe("Site");
  });

  it.each([
    "[click](javascript:alert(1))",
    "[click](JavaScript:alert(1))",
    "[click](data:text/html,<script>alert(1)</script>)",
    "[click](vbscript:msgbox(1))",
    "<javascript:alert(1)>",
  ])("does not make %j clickable", (markdown) => {
    const { container } = render(<CvTextPreview content={markdown} />);

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(container.querySelector("a")).toBeNull();
    expect(container).toHaveTextContent(markdown);
  });

  it("shows HTML as text instead of rendering it", () => {
    const html = '<img src=x onerror="alert(1)"><script>alert(2)</script>';
    const { container } = render(<CvTextPreview content={html} />);

    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container).toHaveTextContent(html);
  });

  it("renders line breaks", () => {
    const { container } = render(<CvTextPreview content={"a\nb"} />);
    expect(container.querySelectorAll("br")).toHaveLength(1);
  });

  it("renders nothing for empty text", () => {
    const { container } = render(<CvTextPreview content="" />);
    expect(container.firstChild).toBeEmptyDOMElement();
  });
});
