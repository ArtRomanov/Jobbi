import {
  buildCvLayout,
  isDateRangeLine,
  parseCvMarkdown,
  type CvBlock,
  type CvInline,
  type CvLayout,
  type CvLayoutItem,
} from "@/entities/cv";

const text = (value: string): CvInline => ({ kind: "text", text: value });

function inlineText(nodes: readonly CvInline[]): string {
  return nodes
    .map((node) => {
      switch (node.kind) {
        case "text":
          return node.text;
        case "break":
          return "\n";
        default:
          return inlineText(node.children);
      }
    })
    .join("");
}

function blocksText(blocks: readonly CvBlock[]): string {
  return blocks
    .map((block) => {
      switch (block.kind) {
        case "heading":
        case "paragraph":
          return inlineText(block.children);
        case "raw":
          return block.text;
        case "list":
          return block.items.map((item) => blocksText(item.blocks)).join("\n");
      }
    })
    .join("\n");
}

function itemText(item: CvLayoutItem): string {
  if (item.kind === "paragraph") return inlineText(item.children);
  if (item.kind !== "entry") return blocksText([item]);
  return [inlineText(item.title), item.dates ? inlineText(item.dates) : "", ...item.blocks.map(itemText)].join(
    "\n",
  );
}

/** All text of a layout, in reading order. */
function layoutText(layout: CvLayout): string {
  const parts: string[] = [];
  if (layout.header) {
    parts.push(inlineText(layout.header.name));
    if (layout.header.title) parts.push(inlineText(layout.header.title));
    parts.push(...layout.header.contacts.map(inlineText));
  }
  for (const section of layout.sections) {
    if (section.heading) parts.push(inlineText(section.heading));
    parts.push(...section.items.map(itemText));
  }
  return parts.join("\n");
}

/** Words (letters/digits runs) in order: what "no text lost or added" means. */
function words(value: string): string[] {
  return value.match(/[\p{L}\p{N}]+/gu) ?? [];
}

function expectSameText(markdown: string): void {
  expect(words(layoutText(buildCvLayout(markdown)))).toEqual(words(blocksText(parseCvMarkdown(markdown))));
}

const EN_CV = `# Jane Doe
Senior Frontend Engineer
jane@example.com · +1 555 123 4567 · Berlin · https://linkedin.com/in/jane

## Profile
I build **fast** web apps.

## Experience
### Frontend Lead — Acme
Jan 2020 – Present
Fintech platform for SMEs; React, TypeScript.
- **Led:** a team of 5
- Shipped the new checkout

### Engineer — Beta · 2017 – 2019
- Built things

## Skills
**Frontend:** React, TypeScript
**Backend:** Node.js`;

const RU_CV = `# Иван Петров
Frontend-разработчик
ivan@example.ru | +7 999 123-45-67 | Москва

## Опыт работы
### Ведущий разработчик — ООО «Ромашка»
Март 2019 — по настоящее время
Онлайн-банк; React, Redux.
- **Сделал:** дизайн-систему
- Ускорил сборку в 2 раза

### Разработчик — Яндекс
сентябрь 2016 – февраль 2019
- Поиск

## Образование
МГУ, 2012 — 2016`;

describe("isDateRangeLine", () => {
  it.each([
    "Jan 2020 – Present",
    "January 2020 - present",
    "Sept. 2018 — Dec. 2019",
    "2019 — 2021",
    "2019-2021",
    "2019 – 2021, Remote",
    "Jan 2020 – Present · Berlin",
    "Sep 2019 – May 2021 (1 year 8 months)",
    "01/2019 - 03/2021",
    "2021-01 – 2022-03",
    "03.2019 – 05.2021",
    "since 2020 – now",
    "Март 2019 — по настоящее время",
    "март 2019 – н.в.",
    "Январь 2020 – по н.в.",
    "сентябрь 2016 – февраль 2019",
    "с 2020 по 2022",
    "2020 г. – 2022 г.",
    "Июнь 2021 — сейчас",
    "(2018 – 2020)",
    "Oct 2015 to Mar 2017",
    "2018 – Current",
  ])("matches %j", (line) => {
    expect(isDateRangeLine(line)).toBe(true);
  });

  it.each([
    "",
    "Acme Corp",
    "2019",
    "Built 2019 – 2021 era payment system for a large bank with many many users",
    "Increased revenue by 20% in 2020",
    "React, TypeScript, Node.js",
    "Acme, Berlin | 2020 – 2022",
    "2020 - 2022 " + "x".repeat(80),
    "mayday 2020 - 2021",
  ])("does not match %j", (line) => {
    expect(isDateRangeLine(line)).toBe(false);
  });
});

describe("buildCvLayout", () => {
  it("returns nothing for empty text", () => {
    expect(buildCvLayout("")).toEqual({ header: null, sections: [] });
    expect(buildCvLayout(" \n\n ")).toEqual({ header: null, sections: [] });
  });

  it("builds the header: name, title line and contacts split on ' · '", () => {
    const { header } = buildCvLayout(EN_CV);
    expect(header?.name).toEqual([text("Jane Doe")]);
    expect(header?.title).toEqual([text("Senior Frontend Engineer")]);
    expect(header?.contacts.map(inlineText)).toEqual([
      "jane@example.com",
      "+1 555 123 4567",
      "Berlin",
      "https://linkedin.com/in/jane",
    ]);
    // Bare email and URL stay links
    expect(header?.contacts[0]?.[0]).toMatchObject({ kind: "link", href: "mailto:jane@example.com" });
    expect(header?.contacts[3]?.[0]).toMatchObject({ kind: "link", href: "https://linkedin.com/in/jane" });
  });

  it("splits contacts on ' | ' and line breaks", () => {
    const { header } = buildCvLayout("# Jane\njane@example.com | +1 555 123 4567\nBerlin\nhttps://jane.dev");
    expect(header?.title).toBeNull();
    expect(header?.contacts.map(inlineText)).toEqual([
      "jane@example.com",
      "+1 555 123 4567",
      "Berlin",
      "https://jane.dev",
    ]);
  });

  it("takes contacts from following paragraphs only when every line looks like a contact", () => {
    const layout = buildCvLayout(
      "# Jane\n\nFrontend Engineer\n\njane@example.com\n\nhttps://jane.dev\n\nI like long walks and building software.",
    );
    expect(layout.header?.title).toEqual([text("Frontend Engineer")]);
    expect(layout.header?.contacts.map(inlineText)).toEqual(["jane@example.com", "https://jane.dev"]);
    expect(layout.sections[0]?.items).toEqual([
      { kind: "paragraph", children: [text("I like long walks and building software.")], isContext: false },
    ]);
  });

  it("leaves a long summary under the name as a paragraph", () => {
    const summary =
      "Frontend engineer with ten years of experience building web applications for banks and startups.";
    const layout = buildCvLayout(`# Jane\n${summary}`);
    expect(layout.header).toEqual({ name: [text("Jane")], title: null, contacts: [] });
    expect(layout.sections).toEqual([
      { heading: null, items: [{ kind: "paragraph", children: [text(summary)], isContext: false }] },
    ]);
  });

  it("keeps the lines after the contacts as a paragraph", () => {
    const long = "A long line of prose that is clearly not a contact and goes on for a while, really.";
    const layout = buildCvLayout(`# Jane\nEngineer\njane@example.com\n${long}`);
    expect(layout.header?.contacts.map(inlineText)).toEqual(["jane@example.com"]);
    expect(layout.sections[0]?.items).toEqual([
      { kind: "paragraph", children: [text(long)], isContext: false },
    ]);
  });

  it("does not take a heading or list as the header", () => {
    const layout = buildCvLayout("# Jane\n## Experience\n- one");
    expect(layout.header).toEqual({ name: [text("Jane")], title: null, contacts: [] });
    expect(layout.sections[0]?.heading).toEqual([text("Experience")]);
  });

  it("groups ## sections and ### entries with dates on the title row", () => {
    const layout = buildCvLayout(EN_CV);
    expect(layout.sections.map((s) => s.heading && inlineText(s.heading))).toEqual([
      "Profile",
      "Experience",
      "Skills",
    ]);
    const [lead, engineer] = layout.sections[1]?.items ?? [];
    expect(lead).toMatchObject({
      kind: "entry",
      title: [text("Frontend Lead — Acme")],
      dates: [text("Jan 2020 – Present")],
    });
    // The paragraph between the title and the bullets is the muted context
    expect(lead?.kind === "entry" && lead.blocks[0]).toEqual({
      kind: "paragraph",
      children: [text("Fintech platform for SMEs; React, TypeScript.")],
      isContext: true,
    });
    expect(lead?.kind === "entry" && lead.blocks[1]?.kind).toBe("list");
    // Dates written on the title line after " · "
    expect(engineer).toMatchObject({
      kind: "entry",
      title: [text("Engineer — Beta")],
      dates: [text("2017 – 2019")],
    });
  });

  it("handles a Russian CV", () => {
    const layout = buildCvLayout(RU_CV);
    expect(layout.header?.title).toEqual([text("Frontend-разработчик")]);
    expect(layout.header?.contacts.map(inlineText)).toEqual([
      "ivan@example.ru",
      "+7 999 123-45-67",
      "Москва",
    ]);
    const items = layout.sections[0]?.items ?? [];
    expect(items[0]).toMatchObject({ kind: "entry", dates: [text("Март 2019 — по настоящее время")] });
    expect(items[1]).toMatchObject({ kind: "entry", dates: [text("сентябрь 2016 – февраль 2019")] });
    expectSameText(RU_CV);
  });

  it("leaves an entry without a date line as is (no context without a list)", () => {
    const layout = buildCvLayout("## Projects\n### Jobbi\nA job tracker.\n\nMore text.");
    expect(layout.sections[0]?.items).toEqual([
      {
        kind: "entry",
        title: [text("Jobbi")],
        dates: null,
        blocks: [
          { kind: "paragraph", children: [text("A job tracker.")], isContext: false },
          { kind: "paragraph", children: [text("More text.")], isContext: false },
        ],
      },
    ]);
  });

  it("keeps the rest of the date paragraph after the date line", () => {
    const layout = buildCvLayout("### Dev\n2019 – 2021\nRemote team\n- a");
    const entry = layout.sections[0]?.items[0];
    expect(entry).toMatchObject({ kind: "entry", dates: [text("2019 – 2021")] });
    expect(entry?.kind === "entry" && entry.blocks[0]).toEqual({
      kind: "paragraph",
      children: [text("Remote team")],
      isContext: true,
    });
  });

  it("keeps bold dates as bold", () => {
    const layout = buildCvLayout("### Dev\n**2019 – 2021**");
    expect(layout.sections[0]?.items[0]).toMatchObject({
      dates: [{ kind: "strong", children: [text("2019 – 2021")] }],
      blocks: [],
    });
  });

  it("lays out a CV with no # as sections only", () => {
    const layout = buildCvLayout("Jane Doe\njane@example.com\n\n## Experience\n- a");
    expect(layout.header).toBeNull();
    expect(layout.sections[0]?.heading).toBeNull();
    expect(layout.sections[1]?.heading).toEqual([text("Experience")]);
  });

  it("lays out uploaded plain text (no markup) as plain paragraphs", () => {
    const upload = "JANE DOE\nFrontend Engineer\n\nEXPERIENCE\n\nAcme Corp 2019 – 2021\n• Built the app\n• Led a team";
    const layout = buildCvLayout(upload);
    expect(layout.header).toBeNull();
    expect(layout.sections).toHaveLength(1);
    expect(layout.sections[0]?.items.every((item) => item.kind === "paragraph")).toBe(true);
    expectSameText(upload);
  });

  it("shows a second # and a # that is not first as section headings", () => {
    const layout = buildCvLayout("intro\n# Experience\n- a\n# Skills\nReact");
    expect(layout.header).toBeNull();
    expect(layout.sections.map((s) => s.heading && inlineText(s.heading))).toEqual([
      null,
      "Experience",
      "Skills",
    ]);
  });

  it("keeps raw blocks, ordered lists and nested lists", () => {
    const layout = buildCvLayout("## A\n| a | b |\n|---|---|\n| 1 | 2 |\n\n3. three\n4. four\n- x\n  - y\n\n#### deep");
    const kinds = layout.sections[0]?.items.map((item) => item.kind);
    expect(kinds).toEqual(["raw", "list", "list", "raw"]);
    expect(layout.sections[0]?.items[1]).toMatchObject({ ordered: true, start: 3 });
  });

  it("does not treat a date-like sentence in a paragraph as dates", () => {
    const layout = buildCvLayout("### Dev\nIn 2019 – 2021 I built a bank with many users across Europe and Asia.");
    expect(layout.sections[0]?.items[0]).toMatchObject({ dates: null });
  });
});

// A small seeded generator: the same cases on every run.
function makeRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 2 ** 32;
  };
}

const FRAGMENTS = [
  "# Jane Doe",
  "# Иван Петров",
  "## Experience",
  "## Опыт",
  "### Lead — Acme",
  "### Dev · 2019 – 2021",
  "Jan 2020 – Present",
  "Март 2019 — по н.в.",
  "2018-2020, Remote",
  "Senior Engineer",
  "jane@example.com · +1 555 123 4567 · Berlin",
  "a | b | c",
  "https://github.com/jane",
  "[Site](https://jane.dev)",
  "[bad](javascript:alert(1))",
  "- **Led:** a team",
  "- plain bullet",
  "  - nested",
  "1. first",
  "* star item",
  "**Skills:** React, Vue",
  "*italic* text",
  "Сделал **систему** быстрее",
  "#### Deep heading",
  "| a | b |",
  "<b>html</b>",
  "> quote",
  "```",
  "---",
  "",
  "",
  "plain paragraph line with words",
  "• bullet char from upload",
  "Contact: +7 (999) 123-45-67",
  "2019",
  "&amp; entity &lt;tag&gt;",
];

describe("buildCvLayout keeps every word (property)", () => {
  it.each(EN_CV.split("\n").map((_, i) => i))("prefix of the EN CV (%i lines)", (count) => {
    expectSameText(EN_CV.split("\n").slice(0, count + 1).join("\n"));
  });

  it("holds for 400 random CVs", () => {
    const random = makeRandom(20261125);
    for (let run = 0; run < 400; run += 1) {
      const lineCount = 1 + Math.floor(random() * 25);
      const lines: string[] = [];
      for (let i = 0; i < lineCount; i += 1) {
        lines.push(FRAGMENTS[Math.floor(random() * FRAGMENTS.length)] ?? "");
      }
      const markdown = lines.join("\n");
      try {
        expectSameText(markdown);
      } catch (error: unknown) {
        throw new Error(`Text changed for input:\n${markdown}\n\n${String(error)}`);
      }
    }
  });
});
