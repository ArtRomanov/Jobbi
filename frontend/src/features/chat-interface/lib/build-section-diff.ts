import { buildUnifiedDiff, markAllLines, type DiffRow } from "./build-diff-rows";

/** moved: the same text, but out of its old order among the matched sections. */
export type SectionKind = "changed" | "moved" | "added" | "removed" | "unchanged";

export interface SectionDiff {
  /** The `## ` heading text, or "Header" for the text before the first one. */
  title: string;
  kind: SectionKind;
  rows: DiffRow[];
}

interface Section {
  title: string;
  key: string;
  text: string;
}

/** The title of the text before the first `## ` heading (name, contacts). */
export const HEADER_SECTION_TITLE = "Header";

const SECTION_HEADING = /^ {0,3}##[ \t]+(.+)$/;

function headingTitle(raw: string): string {
  // "## Skills ##" -> "Skills" (an optional closing run of #)
  return raw.replace(/[ \t]+#+[ \t]*$/, "").trim();
}

/** Split a Markdown CV at its `## ` headings; blank text before the first is dropped. */
function splitSections(text: string): Section[] {
  const sections: Section[] = [];
  let title = HEADER_SECTION_TITLE;
  let lines: string[] = [];
  const flush = (): void => {
    const body = lines.join("\n").trim();
    if (body) sections.push({ title, key: title.toLowerCase(), text: body });
  };
  for (const line of text.replace(/\r\n?/g, "\n").split("\n")) {
    const heading = SECTION_HEADING.exec(line);
    if (heading?.[1]) {
      flush();
      title = headingTitle(heading[1]);
      lines = [];
    }
    lines.push(line);
  }
  flush();
  return sections;
}

/**
 * Compare two whole CVs section by section (a `replace_all` card): the new
 * CV's sections in order, each changed / moved / added / unchanged, then the
 * removed ones. Sections match by heading, ignoring case; leading and trailing
 * blank lines do not count as a change. A section with the same text that now
 * comes before one it used to follow is "moved": Accept applies the new order,
 * so the card must show it.
 */
export function buildSectionDiff(beforeText: string, afterText: string): SectionDiff[] {
  const before = splitSections(beforeText);
  const used = new Set<number>();
  const result: SectionDiff[] = [];
  let lastIndex = -1;
  for (const section of splitSections(afterText)) {
    const index = before.findIndex((old, i) => !used.has(i) && old.key === section.key);
    const old = before[index];
    if (old === undefined) {
      result.push({
        title: section.title,
        kind: "added",
        rows: markAllLines(section.text, "added"),
      });
      continue;
    }
    used.add(index);
    const moved = index < lastIndex;
    lastIndex = Math.max(lastIndex, index);
    if (old.text !== section.text) {
      result.push({
        title: section.title,
        kind: "changed",
        rows: buildUnifiedDiff(old.text, section.text),
      });
      continue;
    }
    result.push({
      title: section.title,
      kind: moved ? "moved" : "unchanged",
      rows: markAllLines(section.text, "same"),
    });
  }
  before.forEach((old, i) => {
    if (!used.has(i)) {
      result.push({ title: old.title, kind: "removed", rows: markAllLines(old.text, "removed") });
    }
  });
  return result;
}
