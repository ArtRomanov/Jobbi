import { parseCvMarkdown } from "@/entities/cv";

const text = (value: string) => ({ kind: "text", text: value });

describe("parseCvMarkdown", () => {
  it("returns no blocks for empty or blank text", () => {
    expect(parseCvMarkdown("")).toEqual([]);
    expect(parseCvMarkdown("  \n\n ")).toEqual([]);
  });

  it("parses headings 1–3", () => {
    expect(parseCvMarkdown("# Jane\n## Experience\n### Acme")).toEqual([
      { kind: "heading", level: 1, children: [text("Jane")] },
      { kind: "heading", level: 2, children: [text("Experience")] },
      { kind: "heading", level: 3, children: [text("Acme")] },
    ]);
  });

  it("parses heading 4 (a project under a ### entry)", () => {
    expect(parseCvMarkdown("#### Checkout")).toEqual([
      { kind: "heading", level: 4, children: [text("Checkout")] },
    ]);
  });

  it("shows heading 5+ as typed", () => {
    expect(parseCvMarkdown("##### Deep")).toEqual([{ kind: "raw", text: "##### Deep" }]);
  });

  it("parses paragraphs with bold, italic and nested emphasis", () => {
    expect(parseCvMarkdown("I am **bold** and *italic* and ***both***")).toEqual([
      {
        kind: "paragraph",
        children: [
          text("I am "),
          { kind: "strong", children: [text("bold")] },
          text(" and "),
          { kind: "em", children: [text("italic")] },
          text(" and "),
          { kind: "em", children: [{ kind: "strong", children: [text("both")] }] },
        ],
      },
    ]);
  });

  it("keeps single line breaks inside a paragraph", () => {
    expect(parseCvMarkdown("line one\nline two")).toEqual([
      { kind: "paragraph", children: [text("line one"), { kind: "break" }, text("line two")] },
    ]);
  });

  it("separates paragraphs on blank lines", () => {
    expect(parseCvMarkdown("first\n\nsecond")).toEqual([
      { kind: "paragraph", children: [text("first")] },
      { kind: "paragraph", children: [text("second")] },
    ]);
  });

  it("parses bullet lists with nested lists", () => {
    expect(parseCvMarkdown("- React\n- **TypeScript**\n  - strict")).toEqual([
      {
        kind: "list",
        ordered: false,
        start: 1,
        items: [
          { blocks: [{ kind: "paragraph", children: [text("React")] }] },
          {
            blocks: [
              { kind: "paragraph", children: [{ kind: "strong", children: [text("TypeScript")] }] },
              {
                kind: "list",
                ordered: false,
                start: 1,
                items: [{ blocks: [{ kind: "paragraph", children: [text("strict")] }] }],
              },
            ],
          },
        ],
      },
    ]);
  });

  it("parses ordered lists and keeps their start number", () => {
    expect(parseCvMarkdown("3. third\n4. fourth")).toEqual([
      {
        kind: "list",
        ordered: true,
        start: 3,
        items: [
          { blocks: [{ kind: "paragraph", children: [text("third")] }] },
          { blocks: [{ kind: "paragraph", children: [text("fourth")] }] },
        ],
      },
    ]);
  });

  it("parses Markdown links, bare URLs and bare emails", () => {
    expect(
      parseCvMarkdown("[GitHub](https://github.com/jane) · https://jane.dev · www.jane.dev · jane@example.com"),
    ).toEqual([
      {
        kind: "paragraph",
        children: [
          { kind: "link", href: "https://github.com/jane", children: [text("GitHub")] },
          text(" · "),
          { kind: "link", href: "https://jane.dev", children: [text("https://jane.dev")] },
          text(" · "),
          { kind: "link", href: "http://www.jane.dev", children: [text("www.jane.dev")] },
          text(" · "),
          { kind: "link", href: "mailto:jane@example.com", children: [text("jane@example.com")] },
        ],
      },
    ]);
  });

  it.each([
    "[click](javascript:alert(1))",
    "[click](JAVASCRIPT:alert(1))",
    "[click](data:text/html,hi)",
    "[click](vbscript:msgbox)",
    "[click](/relative)",
    "<javascript:alert(1)>",
  ])("keeps unsafe link %j as plain text", (markdown) => {
    const blocks = parseCvMarkdown(markdown);
    expect(blocks).toEqual([{ kind: "paragraph", children: [text(markdown)] }]);
  });

  it("shows HTML as typed", () => {
    expect(parseCvMarkdown('<script>alert("x")</script>')).toEqual([
      { kind: "raw", text: '<script>alert("x")</script>' },
    ]);
    expect(parseCvMarkdown("a <b>tag</b> here")).toEqual([
      { kind: "paragraph", children: [text("a <b>tag</b> here")] },
    ]);
  });

  it.each([
    ["table", "| a | b |\n| - | - |\n| 1 | 2 |"],
    ["code block", "```\nconst x = 1;\n```"],
    ["blockquote", "> quoted"],
    ["horizontal rule", "---"],
  ])("shows a %s as typed", (_name, markdown) => {
    expect(parseCvMarkdown(markdown)).toEqual([{ kind: "raw", text: markdown }]);
  });

  it("shows inline images, code and strikethrough as typed", () => {
    expect(parseCvMarkdown("![logo](https://x.dev/a.png) `npm` ~~old~~")).toEqual([
      { kind: "paragraph", children: [text("![logo](https://x.dev/a.png) `npm` ~~old~~")] },
    ]);
  });

  it("shows task-list checkboxes as typed", () => {
    expect(parseCvMarkdown("- [x] done")).toEqual([
      {
        kind: "list",
        ordered: false,
        start: 1,
        items: [{ blocks: [{ kind: "paragraph", children: [text("[x] done")] }] }],
      },
    ]);
  });

  it("unescapes backslash escapes", () => {
    expect(parseCvMarkdown("\\*not italic\\*")).toEqual([
      { kind: "paragraph", children: [text("*not italic*")] },
    ]);
  });

  it("handles Cyrillic text in every construct", () => {
    expect(
      parseCvMarkdown("# Иван Петров\n## Опыт\n- **Ведущий** *инженер*\n\n[Профиль](https://hh.ru/резюме)"),
    ).toEqual([
      { kind: "heading", level: 1, children: [text("Иван Петров")] },
      { kind: "heading", level: 2, children: [text("Опыт")] },
      {
        kind: "list",
        ordered: false,
        start: 1,
        items: [
          {
            blocks: [
              {
                kind: "paragraph",
                children: [
                  { kind: "strong", children: [text("Ведущий")] },
                  text(" "),
                  { kind: "em", children: [text("инженер")] },
                ],
              },
            ],
          },
        ],
      },
      {
        kind: "paragraph",
        children: [{ kind: "link", href: "https://hh.ru/резюме", children: [text("Профиль")] }],
      },
    ]);
  });

  it.each([
    "[x](&#106;avascript:alert(1))",
    "[x](&#x6A;avascript:alert(1))",
    "[x](java&#x73;cript:alert(1))",
    "[x](javascript&colon;alert(1))",
    "[x](&#100;ata:text/html,hi)",
  ])("keeps entity-encoded unsafe scheme %j as plain text", (markdown) => {
    expect(parseCvMarkdown(markdown)).toEqual([{ kind: "paragraph", children: [text(markdown)] }]);
  });

  it("resolves reference-style links and does not print their definitions", () => {
    expect(parseCvMarkdown("See [my site][1].\n\n[1]: https://jane.dev")).toEqual([
      {
        kind: "paragraph",
        children: [
          text("See "),
          { kind: "link", href: "https://jane.dev", children: [text("my site")] },
          text("."),
        ],
      },
    ]);
  });

  it("keeps a reference-style link with an unsafe definition as plain text", () => {
    expect(parseCvMarkdown("[click][x]\n\n[x]: javascript:alert(1)")).toEqual([
      { kind: "paragraph", children: [text("[click][x]")] },
    ]);
  });

  it("parses <https://…> and <mailto:…> autolinks", () => {
    expect(parseCvMarkdown("<https://jane.dev/cv> <mailto:jane@example.com>")).toEqual([
      {
        kind: "paragraph",
        children: [
          { kind: "link", href: "https://jane.dev/cv", children: [text("https://jane.dev/cv")] },
          text(" "),
          { kind: "link", href: "mailto:jane@example.com", children: [text("mailto:jane@example.com")] },
        ],
      },
    ]);
  });

  it("decodes basic HTML entities in displayed text", () => {
    expect(parseCvMarkdown("R&amp;D &lt;team&gt; &quot;Q&quot; &#39;s&#39; &#1046; &#x416;")).toEqual([
      { kind: "paragraph", children: [text(`R&D <team> "Q" 's' Ж Ж`)] },
    ]);
  });

  it("leaves named entities other than the basic ones as typed", () => {
    expect(parseCvMarkdown("&nbsp; &copy; &#99999999;")).toEqual([
      { kind: "paragraph", children: [text("&nbsp; &copy; &#99999999;")] },
    ]);
  });

  it("shows invalid numeric code points as the replacement character (CommonMark)", () => {
    expect(parseCvMarkdown("&#0; &#xD800;")).toEqual([
      { kind: "paragraph", children: [text("\uFFFD \uFFFD")] },
    ]);
  });
});
