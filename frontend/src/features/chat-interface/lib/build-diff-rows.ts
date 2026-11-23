import { diffLines } from "diff";

export type DiffRowKind = "same" | "removed" | "added";

export interface DiffRow {
  kind: DiffRowKind;
  text: string;
}

export interface CardDiff {
  /** The passage as it is now: unchanged + removed lines. */
  before: DiffRow[];
  /** The proposed passage: unchanged + added lines. */
  after: DiffRow[];
}

/** Split a diff chunk into lines; a trailing newline does not make an extra empty line. */
function splitLines(value: string): string[] {
  const lines = value.split("\n");
  if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
  return lines;
}

/** Every line of `text` marked with one kind (an insertion or a removal). */
export function markAllLines(text: string, kind: DiffRowKind): DiffRow[] {
  return splitLines(text).map((line) => ({ kind, text: line }));
}

/** Line-level diff of a replace card, split into a "before" and an "after" column. */
export function buildCardDiff(beforeText: string, afterText: string): CardDiff {
  const before: DiffRow[] = [];
  const after: DiffRow[] = [];
  for (const change of diffLines(beforeText, afterText)) {
    for (const line of splitLines(change.value)) {
      if (change.removed) {
        before.push({ kind: "removed", text: line });
      } else if (change.added) {
        after.push({ kind: "added", text: line });
      } else {
        before.push({ kind: "same", text: line });
        after.push({ kind: "same", text: line });
      }
    }
  }
  return { before, after };
}
