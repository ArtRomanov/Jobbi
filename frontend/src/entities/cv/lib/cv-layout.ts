import { isDateRangeLine } from "./cv-date-range";
import {
  hasLink,
  hasSeparator,
  inlineText,
  joinLines,
  splitLines,
  splitOnSeparators,
  trimInlines,
} from "./cv-inlines";
import { parseCvMarkdown, type CvBlock, type CvInline, type CvListItem } from "./cv-markdown";

/**
 * Layout of a CV for the designed views (editor preview and "Download HTML").
 * Built from `parseCvMarkdown` blocks: it only decides WHERE existing text
 * goes (header, sections, entries with dates on the right); it never adds,
 * removes or reorders words. Contact separators (" | ", " • ") are shown as
 * " · ". Whatever matches no rule stays a plain block.
 */
export interface CvLayout {
  /** Present only when the CV starts with `# Name`. */
  header: CvLayoutHeader | null;
  sections: CvLayoutSection[];
}

export interface CvLayoutHeader {
  name: CvInline[];
  /** The line under the name ("Senior Frontend Engineer"), if any. */
  title: CvInline[] | null;
  /** One part per contact; the renderer joins them with " · " in one line. */
  contacts: CvInline[][];
}

export interface CvLayoutSection {
  /** `## Heading`; null for the blocks before the first section. */
  heading: CvInline[] | null;
  items: CvLayoutItem[];
}

export type CvLayoutBlock =
  /** `isContext`: a paragraph between an entry title and its bullet list (shown muted). */
  | { kind: "paragraph"; children: CvInline[]; isContext: boolean }
  | { kind: "list"; ordered: boolean; start: number; items: CvListItem[] }
  | { kind: "raw"; text: string };

export interface CvLayoutEntry {
  kind: "entry";
  /** `### Title`. */
  title: CvInline[];
  /** The date range shown at the right of the title row. */
  dates: CvInline[] | null;
  /**
   * What separated title and dates in the text (" · " / " | " on the title
   * line, " " for a dates line of its own); null without dates. The views
   * keep it in the text, visually hidden, so title and dates never glue
   * together ("EngineerJan") when the text is copied or read out.
   */
  datesSeparator: string | null;
  blocks: CvLayoutBlock[];
}

export type CvLayoutItem = CvLayoutBlock | CvLayoutEntry;

/** The longest line that may be the title under the name. */
const MAX_TITLE_LENGTH = 80;
/** A header line with no contact sign (e.g. "Berlin, Germany") must be this short. */
const MAX_PLAIN_CONTACT_LENGTH = 60;
const EMAIL_SIGN = /\S@\S/u;
const PHONE_SIGN = /\+?\d[\d\s().-]{6,}\d/u;
// "2016 - 2024", "03.2016-12.2024": digits a phone would also match, but a date.
// Removed before the phone check so a summary line with years is not a contact.
const YEAR_RANGE = /(?<![\d.])(?:\d{1,2}[./])?(?:19|20)\d{2}\s*[-–—]\s*(?:\d{1,2}[./])?(?:19|20)\d{2}(?![\d.])/gu;
// `(?<![\w-])`: start only at the beginning of a word, so a long run of
// letters is scanned once, not once per letter (quadratic on a 20 000-char line)
const WEB_SIGN = /(?:https?:\/\/|www\.)\S|(?<![\w-])[\w-]+\.(?:com|io|dev|me|org|net|ru)\/\S/iu;

/** An email, phone number or link/URL: what makes header lines "contacts". */
function hasContactSign(line: readonly CvInline[]): boolean {
  const text = inlineText(line);
  return (
    hasLink(line) ||
    EMAIL_SIGN.test(text) ||
    PHONE_SIGN.test(text.replace(YEAR_RANGE, " ")) ||
    WEB_SIGN.test(text)
  );
}

function isContactLike(line: readonly CvInline[]): boolean {
  return hasContactSign(line) || hasSeparator(line);
}

function lineLength(line: readonly CvInline[]): number {
  return inlineText(line).trim().length;
}

function isBlankLine(line: readonly CvInline[]): boolean {
  return lineLength(line) === 0;
}

function toParagraph(children: CvInline[]): CvLayoutBlock {
  return { kind: "paragraph", children, isContext: false };
}

interface HeaderResult {
  header: CvLayoutHeader;
  /** Blocks after the header that are not part of it (in order). */
  rest: CvBlock[];
}

/**
 * `# Name`, then the first paragraph: its first line is the title unless it
 * looks like a contact; the following short / contact-like lines are the
 * contacts. Further paragraphs join the contacts only when every line in them
 * looks like a contact. Anything else stays a normal block after the header.
 *
 * Title and contacts come as a pair: they are taken only when the contact
 * lines hold a real contact (email, phone, link/URL). Otherwise nothing under
 * the name is guessed: the name stands alone and the lines stay normal text,
 * so a summary or a skills line never becomes the big title or "contacts".
 */
function buildHeader(name: CvInline[], blocks: readonly CvBlock[]): HeaderResult {
  const header: CvLayoutHeader = { name, title: null, contacts: [] };
  const nameOnly: HeaderResult = { header: { name, title: null, contacts: [] }, rest: [...blocks] };
  let index = 0;
  const leftover: CvBlock[] = [];
  let hasRealContact = false;

  const first = blocks[0];
  if (first?.kind === "paragraph") {
    const lines = splitLines(first.children).filter((line) => !isBlankLine(line));
    let lineIndex = 0;
    const titleLine = lines[0];
    if (titleLine && !isContactLike(titleLine) && lineLength(titleLine) <= MAX_TITLE_LENGTH) {
      header.title = trimInlines(titleLine);
      lineIndex = 1;
    }
    for (let line = lines[lineIndex]; line !== undefined; line = lines[lineIndex]) {
      if (!isContactLike(line) && lineLength(line) > MAX_PLAIN_CONTACT_LENGTH) break;
      header.contacts.push(...splitOnSeparators(line));
      hasRealContact ||= hasContactSign(line);
      lineIndex += 1;
    }
    if (lineIndex === 0) {
      // Nothing matched (e.g. a long summary right under the name): leave it be
      return nameOnly;
    }
    index = 1;
    if (lineIndex < lines.length) {
      leftover.push({ kind: "paragraph", children: joinLines(lines.slice(lineIndex)) });
    } else {
      // Whole first paragraph used: following all-contact paragraphs join in
      for (let block = blocks[index]; block !== undefined; block = blocks[index]) {
        if (block.kind !== "paragraph") break;
        const blockLines = splitLines(block.children).filter((line) => !isBlankLine(line));
        if (blockLines.length === 0 || !blockLines.every(isContactLike)) break;
        if (!blockLines.some(hasContactSign)) break;
        for (const line of blockLines) header.contacts.push(...splitOnSeparators(line));
        hasRealContact = true;
        index += 1;
      }
    }
  }
  if (!hasRealContact) return nameOnly;
  return { header, rest: [...leftover, ...blocks.slice(index)] };
}

interface TitleSplit {
  title: CvInline[];
  dates: CvInline[] | null;
  datesSeparator: string | null;
}

/** "### Engineer · Jan 2020 – Present": the date range after the last " · " / " | ". */
function splitTitleDates(title: CvInline[]): TitleSplit {
  const noDates: TitleSplit = { title, dates: null, datesSeparator: null };
  const last = title[title.length - 1];
  if (last?.kind !== "text") return noDates;
  const match = /^(.*\S)(\s+[·|]\s+)(\S.*)$/su.exec(last.text);
  const [, before, separator, dates] = match ?? [];
  if (before === undefined || separator === undefined || dates === undefined || !isDateRangeLine(dates)) {
    return noDates;
  }
  return {
    title: [...title.slice(0, -1), { kind: "text", text: before }],
    dates: [{ kind: "text", text: dates }],
    datesSeparator: separator,
  };
}

/** Stands for the line break between a title and a dates line of its own. */
const DATES_LINE_SEPARATOR = " ";

function toLayoutBlock(block: CvBlock): CvLayoutBlock | null {
  switch (block.kind) {
    case "paragraph":
      return toParagraph(block.children);
    case "list":
      return block;
    case "raw":
      return block;
    case "heading":
      return null;
  }
}

/** An entry: `### Title`, its dates (title row or the next line), then its blocks. */
function buildEntry(heading: CvInline[], blocks: readonly CvBlock[]): CvLayoutEntry {
  const split = splitTitleDates(heading);
  const entry: CvLayoutEntry = { kind: "entry", ...split, blocks: [] };
  const body = [...blocks];

  const first = body[0];
  if (entry.dates === null && first?.kind === "paragraph") {
    const [firstLine = [], ...rest] = splitLines(first.children);
    if (isDateRangeLine(inlineText(firstLine))) {
      entry.dates = trimInlines(firstLine);
      entry.datesSeparator = DATES_LINE_SEPARATOR;
      body.shift();
      if (rest.some((line) => !isBlankLine(line))) {
        body.unshift({ kind: "paragraph", children: joinLines(rest) });
      }
    }
  }

  // Paragraphs between the title and the first list are its muted context
  const firstListIndex = body.findIndex((block) => block.kind === "list");
  body.forEach((block, index) => {
    const layoutBlock = toLayoutBlock(block);
    if (!layoutBlock) return;
    if (layoutBlock.kind === "paragraph" && firstListIndex > index) {
      const onlyParagraphsBefore = body.slice(0, index).every((b) => b.kind === "paragraph");
      if (onlyParagraphsBefore) layoutBlock.isContext = true;
    }
    entry.blocks.push(layoutBlock);
  });
  return entry;
}

/** Splits a section's blocks into plain blocks and `###` entries. */
function buildSectionItems(blocks: readonly CvBlock[]): CvLayoutItem[] {
  const items: CvLayoutItem[] = [];
  let index = 0;
  for (let block = blocks[index]; block !== undefined; block = blocks[index]) {
    if (block.kind === "heading" && block.level === 3) {
      let end = index + 1;
      while (end < blocks.length && blocks[end]?.kind !== "heading") end += 1;
      items.push(buildEntry(block.children, blocks.slice(index + 1, end)));
      index = end;
      continue;
    }
    const layoutBlock = toLayoutBlock(block);
    if (layoutBlock) items.push(layoutBlock);
    index += 1;
  }
  return items;
}

/**
 * Groups blocks into sections. `##` starts a section; a `#` that is not the
 * name (a second one, or one not at the top) is shown as a section heading too.
 */
function buildSections(blocks: readonly CvBlock[]): CvLayoutSection[] {
  const sections: CvLayoutSection[] = [];
  let current: { heading: CvInline[] | null; blocks: CvBlock[] } = { heading: null, blocks: [] };
  const flush = (): void => {
    if (current.heading !== null || current.blocks.length > 0) {
      sections.push({ heading: current.heading, items: buildSectionItems(current.blocks) });
    }
  };
  for (const block of blocks) {
    if (block.kind === "heading" && block.level !== 3) {
      flush();
      current = { heading: block.children, blocks: [] };
    } else {
      current.blocks.push(block);
    }
  }
  flush();
  return sections;
}

/** Lays out parsed CV blocks (see `CvLayout`). Never throws, never loses text. */
export function buildCvLayoutFromBlocks(blocks: readonly CvBlock[]): CvLayout {
  const first = blocks[0];
  if (first?.kind === "heading" && first.level === 1) {
    const { header, rest } = buildHeader(first.children, blocks.slice(1));
    return { header, sections: buildSections(rest) };
  }
  return { header: null, sections: buildSections(blocks) };
}

/** Parses CV Markdown and lays it out for the designed views. */
export function buildCvLayout(markdown: string): CvLayout {
  return buildCvLayoutFromBlocks(parseCvMarkdown(markdown));
}
