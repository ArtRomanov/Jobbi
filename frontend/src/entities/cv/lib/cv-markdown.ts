import { Lexer } from "marked";
import type { Token, Tokens } from "marked";
import { isSafeCvLinkUrl } from "@/shared/lib";

/**
 * Renderer-neutral model of a CV text. The preview (React DOM) and the PDF
 * (react-pdf) both render THIS model, so the supported formatting cannot drift
 * between them (tech spec 2.5 "Markdown parity").
 */
export type CvInline =
  | { kind: "text"; text: string }
  | { kind: "strong"; children: CvInline[] }
  | { kind: "em"; children: CvInline[] }
  | { kind: "link"; href: string; children: CvInline[] }
  | { kind: "break" };

/** `#`–`####`; `####` is a project under a `###` employer entry. Deeper levels stay raw. */
export type CvHeadingLevel = 1 | 2 | 3 | 4;

export type CvBlock =
  | { kind: "heading"; level: CvHeadingLevel; children: CvInline[] }
  | { kind: "paragraph"; children: CvInline[] }
  | { kind: "list"; ordered: boolean; start: number; items: CvListItem[] }
  /** Any unsupported markup (tables, HTML, images, code, quotes, rules…), shown exactly as typed. */
  | { kind: "raw"; text: string };

export interface CvListItem {
  blocks: CvBlock[];
}

// One lexer configuration for the whole app. GFM turns bare web and email
// addresses into links; `breaks` keeps single line breaks (CV contact lines,
// text extracted from uploads) instead of joining them into one line.
const LEXER_OPTIONS = { gfm: true, breaks: true } as const;

function stripTrailingNewlines(raw: string): string {
  return raw.replace(/\n+$/, "");
}

const NAMED_ENTITIES: Readonly<Record<string, string>> = {
  amp: "&",
  lt: "<",
  gt: ">",
  quot: '"',
};
const ENTITY_PATTERN = /&(?:#(\d{1,7})|#[xX]([0-9a-fA-F]{1,6})|(amp|lt|gt|quot));/g;

function decodeCodePoint(codePoint: number, original: string): string {
  const isValid =
    codePoint > 0 &&
    codePoint <= 0x10ffff &&
    !(codePoint >= 0xd800 && codePoint <= 0xdfff);
  return isValid ? String.fromCodePoint(codePoint) : original;
}

/**
 * Decodes only the basic HTML entities (&amp; &lt; &gt; &quot;, &#NN; and
 * &#xNN;) for DISPLAY text. Never applied to link targets: hrefs are checked
 * by `isSafeCvLinkUrl` exactly as typed, so "&#106;avascript:" stays unsafe.
 */
function decodeBasicEntities(text: string): string {
  if (!text.includes("&")) return text;
  return text.replace(ENTITY_PATTERN, (match, dec?: string, hex?: string, name?: string) => {
    if (dec !== undefined) return decodeCodePoint(Number.parseInt(dec, 10), match);
    if (hex !== undefined) return decodeCodePoint(Number.parseInt(hex, 16), match);
    return (name !== undefined && NAMED_ENTITIES[name]) || match;
  });
}

function isHeadingLevel(depth: number): depth is CvHeadingLevel {
  return depth === 1 || depth === 2 || depth === 3 || depth === 4;
}

/** Joins neighbouring text nodes so renderers get fewer, larger runs. */
function pushInline(out: CvInline[], node: CvInline): void {
  const last = out[out.length - 1];
  if (node.kind === "text" && last?.kind === "text") {
    out[out.length - 1] = { kind: "text", text: last.text + node.text };
    return;
  }
  if (node.kind === "text" && node.text === "") return;
  out.push(node);
}

function walkInline(tokens: readonly Token[]): CvInline[] {
  const out: CvInline[] = [];
  for (const token of tokens) {
    switch (token.type) {
      case "text": {
        const text = token as Tokens.Text;
        if (text.tokens && text.tokens.length > 0) {
          for (const child of walkInline(text.tokens)) pushInline(out, child);
        } else {
          pushInline(out, { kind: "text", text: decodeBasicEntities(text.text) });
        }
        break;
      }
      case "escape":
        pushInline(out, { kind: "text", text: (token as Tokens.Escape).text });
        break;
      case "strong":
        pushInline(out, {
          kind: "strong",
          children: walkInline((token as Tokens.Strong).tokens),
        });
        break;
      case "em":
        pushInline(out, {
          kind: "em",
          children: walkInline((token as Tokens.Em).tokens),
        });
        break;
      case "br":
        pushInline(out, { kind: "break" });
        break;
      case "link": {
        const link = token as Tokens.Link;
        if (isSafeCvLinkUrl(link.href)) {
          pushInline(out, {
            kind: "link",
            href: link.href,
            children: walkInline(link.tokens),
          });
        } else {
          // Not a web or email link: show what the user typed, not clickable.
          pushInline(out, { kind: "text", text: link.raw });
        }
        break;
      }
      default:
        // codespan, del, inline html, image, checkbox, …: shown as typed.
        pushInline(out, { kind: "text", text: token.raw });
    }
  }
  return out;
}

function walkListItem(item: Tokens.ListItem): CvListItem {
  const blocks: CvBlock[] = [];
  // Tight list items hold bare block-level "text" tokens; group consecutive
  // ones into a paragraph so every item renders as blocks.
  let pending: CvInline[] | null = null;
  const flush = (): void => {
    if (pending && pending.length > 0) {
      blocks.push({ kind: "paragraph", children: pending });
    }
    pending = null;
  };

  for (const token of item.tokens) {
    if (token.type === "text" || token.type === "checkbox") {
      pending ??= [];
      // A task checkbox has no CV meaning: its raw ("[x] ") stays as typed.
      for (const node of walkInline([token])) pushInline(pending, node);
      continue;
    }
    flush();
    blocks.push(...walkBlocks([token]));
  }
  flush();
  return { blocks };
}

function walkBlocks(tokens: readonly Token[]): CvBlock[] {
  const out: CvBlock[] = [];
  for (const token of tokens) {
    switch (token.type) {
      case "space":
      // Reference definitions ("[1]: https://…") only feed reference-style
      // links; like in rendered Markdown they are not printed themselves.
      case "def":
        break;
      case "heading": {
        const heading = token as Tokens.Heading;
        if (isHeadingLevel(heading.depth)) {
          out.push({
            kind: "heading",
            level: heading.depth,
            children: walkInline(heading.tokens),
          });
        } else {
          out.push({ kind: "raw", text: stripTrailingNewlines(heading.raw) });
        }
        break;
      }
      case "paragraph":
        out.push({
          kind: "paragraph",
          children: walkInline((token as Tokens.Paragraph).tokens),
        });
        break;
      case "text": {
        // Top-level block text (rare outside lists): treat as a paragraph.
        const text = token as Tokens.Text;
        out.push({
          kind: "paragraph",
          children: walkInline(text.tokens ?? [{ type: "text", raw: text.raw, text: text.text }]),
        });
        break;
      }
      case "list": {
        const list = token as Tokens.List;
        out.push({
          kind: "list",
          ordered: list.ordered,
          start: typeof list.start === "number" ? list.start : 1,
          items: list.items.map(walkListItem),
        });
        break;
      }
      default: {
        // table, html, code, blockquote, hr, def, …: shown exactly as typed.
        const text = stripTrailingNewlines(token.raw);
        if (text !== "") out.push({ kind: "raw", text });
      }
    }
  }
  return out;
}

/** Parses CV text into the shared block model. Never throws on user input. */
export function parseCvMarkdown(content: string): CvBlock[] {
  return walkBlocks(new Lexer(LEXER_OPTIONS).lex(content));
}

