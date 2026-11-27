import { buildUnifiedDiff, markAllLines, type DiffRow } from "./build-diff-rows";

export type SectionKind = "changed" | "added" | "removed" | "unchanged";

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
 * CV's sections in order, each changed / added / unchanged, then the removed
 * ones. Sections match by heading, ignoring case; leading and trailing blank
 * lines do not count as a change.
 */
export function buildSectionDiff(beforeText: string, afterText: string): SectionDiff[] {
  const before = splitSections(beforeText);
  const used = new Set<number>();
  const result: SectionDiff[] = [];
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
    result.push(
      old.text === section.text
        ? { title: section.title, kind: "unchanged", rows: markAllLines(section.text, "same") }
        : { title: section.title, kind: "changed", rows: buildUnifiedDiff(old.text, section.text) },
    );
  }
  before.forEach((old, i) => {
    if (!used.has(i)) {
      result.push({ title: old.title, kind: "removed", rows: markAllLines(old.text, "removed") });
    }
  });
  return result;
}
