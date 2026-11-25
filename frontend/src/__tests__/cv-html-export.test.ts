import { buildCvFontFaceCss, buildCvLayout, CV_FONT_FILES } from "@/entities/cv";
import { downloadCvHtml, getCvHtmlFileName } from "@/features/cv-html-export";
// Lazy-only modules (see features/cv-html-export/CLAUDE.md): tests read them directly
import { CV_FONT_DATA_URLS } from "@/features/cv-html-export/lib/cv-font-data-urls";
import { escapeHtml, renderCvHtml } from "@/features/cv-html-export/lib/render-cv-html";

const CV = `# Jane Doe
Senior Frontend Engineer
jane@example.com · https://github.com/jane · Berlin

## Experience
### Lead — Acme
Jan 2020 – Present
Fintech; React.
- **Led:** a team of 5
- Shipped [checkout](https://acme.com/checkout)

## Skills
**Frontend:** React`;

function parse(html: string): Document {
  return new DOMParser().parseFromString(html, "text/html");
}

function render(markdown: string, title = "My CV"): string {
  return renderCvHtml(buildCvLayout(markdown), { title });
}

/** Text of every text node, space-joined (block elements have no whitespace between them). */
function textNodes(root: Node): string {
  const walker = root.ownerDocument!.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const parts: string[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) parts.push(node.textContent ?? "");
  return parts.join(" ");
}

/** Words of the visible body text, in order. */
function words(value: string): string[] {
  return value.match(/[\p{L}\p{N}]+/gu) ?? [];
}

describe("renderCvHtml", () => {
  it("returns a complete standalone document with the CV name as title", () => {
    const html = render(CV, "Jane — Frontend");
    expect(html.startsWith("<!DOCTYPE html>")).toBe(true);
    const doc = parse(html);
    expect(doc.title).toBe("Jane — Frontend");
    expect(doc.querySelector('meta[charset="utf-8"]')).not.toBeNull();
    expect(doc.querySelector("style")?.textContent).toContain("@page{size:A4;margin:12mm 15mm}");
    expect(doc.querySelectorAll("script")).toHaveLength(0);
    expect(doc.querySelector('meta[http-equiv="Content-Security-Policy"]')?.getAttribute("content")).toContain(
      "default-src 'none'",
    );
  });

  it("lays out the header, sections and entries with the design classes", () => {
    const doc = parse(render(CV));
    expect(doc.querySelector("h1.cv-name")?.textContent).toBe("Jane Doe");
    expect(doc.querySelector(".cv-title")?.textContent).toBe("Senior Frontend Engineer");
    expect(doc.querySelector(".cv-contacts")?.textContent).toBe(
      "jane@example.com · https://github.com/jane · Berlin",
    );
    expect([...doc.querySelectorAll("h2.cv-section-heading")].map((h) => h.textContent)).toEqual([
      "Experience",
      "Skills",
    ]);
    const head = doc.querySelector(".cv-entry-head");
    expect(head?.querySelector("h3.cv-entry-title")?.textContent).toBe("Lead — Acme");
    // The dates line was on its own line: a hidden space keeps "Acme Jan" apart in the text
    expect(head?.textContent).toBe("Lead — Acme Jan 2020 – Present");
    expect(head?.querySelector(".cv-entry-dates > .cv-hidden-text")?.textContent).toBe(" ");
    expect(head?.querySelector(".cv-entry-dates")?.lastChild?.textContent).toBe("Jan 2020 – Present");
    expect(doc.querySelector(".cv-context")?.textContent).toBe("Fintech; React.");
    expect(doc.querySelectorAll("ul.cv-list > li")).toHaveLength(2);
    expect(doc.querySelector("li strong")?.textContent).toBe("Led:");
  });

  it("keeps the separator between a title and its dates in the text, hidden from view", () => {
    const head = parse(render("### Engineer · Jan 2020 – Present\n- a")).querySelector(".cv-entry-head");
    expect(head?.textContent).toBe("Engineer · Jan 2020 – Present");
    expect(head?.querySelector(".cv-entry-title")?.textContent).toBe("Engineer");
    expect(head?.querySelector(".cv-hidden-text")?.textContent).toBe(" · ");
    // The CSS hides it from view (clip), it stays in copied text and for screen readers
    expect(render("")).toMatch(/\.cv-hidden-text\{position:absolute;[^}]*clip:rect\(0 0 0 0\)/);
  });

  it("keeps the ATS reading order: dates under the title, bullet dots not positioned", () => {
    const css = render("");
    const rule = (selector: string): string =>
      css.match(new RegExp(`(?:^|[\\n}])${selector.replace(/[.>]/g, "\\$&")}\\{([^}]*)\\}`))?.[1] ?? "";
    // Right-aligned dates get detached from their title by PDF text extractors
    expect(rule(".cv-entry-head")).toContain("display:block");
    expect(rule(".cv-entry-head")).not.toMatch(/justify-content:space-between|display:flex/);
    expect(rule(".cv-entry-dates")).toContain("display:block");
    expect(rule(".cv-entry-dates")).not.toContain("text-align:right");
    // A positioned <li> or dot makes Chrome paint every bullet last in the PDF
    expect(rule(".cv-list>li")).toContain("padding-left:15pt");
    expect(rule(".cv-list>li")).not.toContain("position:");
    expect(rule(".cv-list>li::before")).toContain("float:left");
    expect(rule(".cv-list>li::before")).not.toContain("position:");
  });

  it("keeps every word of the CV in order", () => {
    const doc = parse(render(CV));
    expect(words(textNodes(doc.body))).toEqual(
      words("Jane Doe Senior Frontend Engineer jane@example.com https://github.com/jane Berlin Experience Lead Acme Jan 2020 Present Fintech React Led a team of 5 Shipped checkout Skills Frontend React"),
    );
  });

  it("keeps links as written, without new-tab text", () => {
    const doc = parse(render(CV));
    const links = [...doc.querySelectorAll("a")].map((a) => [a.textContent, a.getAttribute("href")]);
    expect(links).toEqual([
      ["jane@example.com", "mailto:jane@example.com"],
      ["https://github.com/jane", "https://github.com/jane"],
      ["checkout", "https://acme.com/checkout"],
    ]);
    expect(doc.querySelector("a[target]")).toBeNull();
  });

  it("renders a CV with no # and Cyrillic text", () => {
    const doc = parse(render("Иван Петров\n\n## Опыт\n- Сделал **всё**", "Резюме"));
    expect(doc.title).toBe("Резюме");
    expect(doc.querySelector("header")).toBeNull();
    expect(doc.querySelector("h2")?.textContent).toBe("Опыт");
    expect(doc.body.textContent).toContain("Иван Петров");
  });

  it("renders empty text as an empty sheet", () => {
    const doc = parse(render(""));
    expect(doc.querySelector(".cv-sheet .cv-doc")?.textContent).toBe("");
  });

  describe("hostile input", () => {
    const HOSTILE = [
      "<script>alert(1)</script>",
      '"><img src=x onerror=alert(1)>',
      "</style><script>alert(2)</script>",
      "[click](javascript:alert(3))",
      "[x](JaVaScRiPt:alert(4))",
      "[x](data:text/html,<script>alert(5)</script>)",
      "[x](vbscript:msgbox(6))",
      "<a href=\"javascript:alert(7)\">a</a>",
      "<svg onload=alert(8)>",
      "<iframe src=//evil.example>",
      "&lt;script&gt;alert(9)&lt;/script&gt;",
      "[ok](https://example.com/\"onmouseover=\"alert(10))",
    ].join("\n\n");

    function hostileDoc(): { html: string; doc: Document } {
      const markdown = `# <img src=x onerror=alert(0)>\n${HOSTILE}\n\n## </title><script>x</script>\n### <b onclick=1>t</b>\n2020 – now`;
      const html = renderCvHtml(buildCvLayout(markdown), { title: '</title><script>alert("t")</script>' });
      return { html, doc: parse(html) };
    }

    it("never produces script, event handler, iframe, img or svg elements", () => {
      const { doc } = hostileDoc();
      expect(doc.querySelectorAll("script, iframe, img, svg, object, embed")).toHaveLength(0);
      for (const element of doc.querySelectorAll("*")) {
        for (const attribute of element.attributes) {
          expect(attribute.name.startsWith("on")).toBe(false);
        }
      }
    });

    it("has no raw <script in the file at all", () => {
      const { html } = hostileDoc();
      expect(html.toLowerCase()).not.toContain("<script");
      expect(html.toLowerCase()).not.toContain("<img");
      // Exactly one style element: CV text cannot close it
      expect(html.match(/<\/style/gi)).toHaveLength(1);
    });

    it("links only to http(s) and mailto", () => {
      const { doc } = hostileDoc();
      const hrefs = [...doc.querySelectorAll("[href]")].map((el) => el.getAttribute("href") ?? "");
      for (const href of hrefs) {
        expect(href).toMatch(/^(https?:|mailto:)/);
      }
    });

    it("shows the hostile text as text", () => {
      const { doc } = hostileDoc();
      expect(doc.title).toBe('</title><script>alert("t")</script>');
      expect(doc.querySelector("h1")?.textContent).toBe("<img src=x onerror=alert(0)>");
      expect(doc.body.textContent).toContain("<script>alert(1)</script>");
      expect(doc.body.textContent).toContain("[click](javascript:alert(3))");
    });
  });

  it("escapeHtml covers text and attribute contexts", () => {
    expect(escapeHtml(`<a href="x" title='y'>&</a>`)).toBe(
      "&lt;a href=&quot;x&quot; title=&#39;y&#39;&gt;&amp;&lt;/a&gt;",
    );
  });
});

describe("CV fonts", () => {
  it("embeds every font file as a base64 woff2 data URL", () => {
    for (const { key } of CV_FONT_FILES) {
      expect(CV_FONT_DATA_URLS[key]).toMatch(/^data:font\/woff2;base64,[A-Za-z0-9+/]+=*$/);
    }
    const css = buildCvFontFaceCss(CV_FONT_DATA_URLS);
    expect(css.match(/@font-face/g)).toHaveLength(CV_FONT_FILES.length);
    expect(css).toContain('font-family:"Roboto Condensed"');
    expect(css).toContain('font-family:"Roboto Mono"');
    expect(css).toContain("U+0400-045F");
  });

  it("refuses a font source that could break out of url()", () => {
    const sources = Object.fromEntries(CV_FONT_FILES.map(({ key }) => [key, '/x.woff2") } body{color:red'])) as Record<
      (typeof CV_FONT_FILES)[number]["key"],
      string
    >;
    expect(buildCvFontFaceCss(sources).trim()).toBe("");
  });

  it("keeps a typical CV with fonts under 300 KB", () => {
    const html = renderCvHtml(buildCvLayout(CV.repeat(5)), {
      title: "CV",
      fontCss: buildCvFontFaceCss(CV_FONT_DATA_URLS),
    });
    const bytes = new TextEncoder().encode(html).length;
    expect(bytes).toBeLessThan(300_000);
  });
});

describe("getCvHtmlFileName", () => {
  it.each([
    ["Jane Doe - Frontend (2026)", "Jane Doe - Frontend (2026).html"],
    ["Резюме Иван — Kleos", "Резюме Иван — Kleos.html"],
    ['a/b\\c:d*e?f"g<h>i|j', "a_b_c_d_e_f_g_h_i_j.html"],
    ["CV\u0000\u001f\u007fx", "CV___x.html"],
    ["", "CV.html"],
    ["   ", "CV.html"],
  ])("%j → %j", (name, expected) => {
    expect(getCvHtmlFileName(name)).toBe(expected);
  });
});

describe("downloadCvHtml", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("downloads a text/html Blob named after the CV", async () => {
    let saved: Blob | null = null;
    vi.spyOn(URL, "createObjectURL").mockImplementation((blob) => {
      saved = blob as Blob;
      return "blob:cv";
    });
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const clicks: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicks.push(this.download);
    });

    await downloadCvHtml({ name: " Jane: CV ", content: CV });

    expect(clicks).toEqual(["Jane_ CV.html"]);
    expect(saved).not.toBeNull();
    const blob = saved as unknown as Blob;
    expect(blob.type).toBe("text/html;charset=utf-8");
    const doc = parse(await blob.text());
    expect(doc.title).toBe("Jane: CV");
    expect(doc.querySelector("style")?.textContent).toContain("data:font/woff2;base64,");
  });
});
