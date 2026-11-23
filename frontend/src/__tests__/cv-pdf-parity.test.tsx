import { Children, isValidElement, type ReactElement, type ReactNode } from "react";
import { render } from "@testing-library/react";
import { Link, Text, View } from "@react-pdf/renderer";
import { CvTextPreview } from "@/entities/cv";
import { CvTextDocument } from "@/features/cv-pdf/ui/cv-text-document";

interface ElementProps {
  children?: ReactNode;
  src?: string;
  style?: unknown;
}

/** What a reader gets from a rendering: its text, its links, its list items. */
interface Rendered {
  text: string;
  hrefs: string[];
  listItems: number;
  boldTexts: string[];
  italicTexts: string[];
}

const LIST_MARKER = /^(•|\d+\.)$/;
const squash = (value: string) => value.replace(/\s+/g, "");

function textOf(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (!isValidElement<ElementProps>(node)) return "";
  return Children.toArray(node.props.children).map(textOf).join("");
}

function styleHas(style: unknown, key: string, value: unknown): boolean {
  return typeof style === "object" && style !== null && (style as Record<string, unknown>)[key] === value;
}

/** Walks the react-pdf element tree (all primitives, no components to call). */
function collectPdf(node: ReactNode, out: Rendered, isRowFirst = false): void {
  if (typeof node === "string" || typeof node === "number") {
    out.text += String(node);
    return;
  }
  if (!isValidElement<ElementProps>(node)) return;
  const element = node as ReactElement<ElementProps>;
  const children = Children.toArray(element.props.children);

  if (element.type === Text && isRowFirst && LIST_MARKER.test(textOf(element))) return;
  if (element.type === Link && element.props.src) out.hrefs.push(element.props.src);
  if (element.type === Text && styleHas(element.props.style, "fontWeight", 700)) {
    out.boldTexts.push(textOf(element));
  }
  if (element.type === Text && styleHas(element.props.style, "fontStyle", "italic")) {
    out.italicTexts.push(textOf(element));
  }
  const isRow = element.type === View && styleHas(element.props.style, "flexDirection", "row");
  if (isRow) out.listItems += 1;
  children.forEach((child, index) => collectPdf(child, out, isRow && index === 0));
}

function renderPdf(content: string): Rendered {
  const out: Rendered = { text: "", hrefs: [], listItems: 0, boldTexts: [], italicTexts: [] };
  collectPdf(CvTextDocument({ name: "My CV", content }), out);
  return { ...out, text: squash(out.text) };
}

function renderPreview(content: string): Rendered {
  const { container, unmount } = render(<CvTextPreview content={content} />);
  // Compare what is on screen: drop the screen-reader-only " (opens in new
  // tab)" suffix on preview links (a PDF has no tabs)
  const visible = container.cloneNode(true) as HTMLElement;
  visible.querySelectorAll('a > span[style*="position: absolute"]').forEach((el) => el.remove());
  const result: Rendered = {
    text: squash(visible.textContent ?? ""),
    hrefs: Array.from(container.querySelectorAll("a"), (a) => a.getAttribute("href") ?? ""),
    listItems: container.querySelectorAll("li").length,
    boldTexts: Array.from(container.querySelectorAll("strong"), (el) => el.textContent ?? ""),
    italicTexts: Array.from(container.querySelectorAll("em"), (el) => el.textContent ?? ""),
  };
  unmount();
  return result;
}

const SAMPLE = [
  "# Иван Петров",
  "ivan@example.com · https://ivan.dev · [GitHub](https://github.com/ivan) · [bad](javascript:alert(1))",
  "",
  "## Опыт",
  "### Acme — **Lead** *Engineer*",
  "- Built **fast** things",
  "- Mentored *five* people",
  "  1. nested one",
  "  2. nested two",
  "",
  "3. third",
  "4. fourth",
  "",
  "| a | b |",
  "|---|---|",
  "| 1 | 2 |",
  "",
  "<b>html</b> R&amp;D [ref][1]",
  "",
  "[1]: https://ref.dev",
].join("\n");

describe("preview / PDF parity", () => {
  it("renders the same text, links, list items and emphasis", () => {
    const pdf = renderPdf(SAMPLE);
    const preview = renderPreview(SAMPLE);

    expect(pdf.text).toBe(preview.text);
    expect(pdf.hrefs).toEqual(preview.hrefs);
    expect(pdf.hrefs).toEqual([
      "mailto:ivan@example.com",
      "https://ivan.dev",
      "https://github.com/ivan",
      "https://ref.dev",
    ]);
    expect(pdf.listItems).toBe(preview.listItems);
    expect(pdf.listItems).toBe(6);
    expect(pdf.italicTexts).toEqual(preview.italicTexts);
    // PDF headings are bold too; the inline <strong> runs must match.
    expect(pdf.boldTexts).toEqual(expect.arrayContaining(preview.boldTexts));
  });

  it("prints only the CV name for an empty text", () => {
    const pdf = renderPdf("   \n");
    expect(pdf.text).toBe(squash("My CV"));
    expect(pdf.hrefs).toEqual([]);
  });

  it("does not print the CV name when there is text", () => {
    expect(renderPdf("Hello").text).toBe("Hello");
  });
});
