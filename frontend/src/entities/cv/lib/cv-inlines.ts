import type { CvInline } from "./cv-markdown";

/** Plain text of inline nodes (a line break counts as "\n"). */
export function inlineText(nodes: readonly CvInline[]): string {
  let out = "";
  for (const node of nodes) {
    switch (node.kind) {
      case "text":
        out += node.text;
        break;
      case "break":
        out += "\n";
        break;
      default:
        out += inlineText(node.children);
    }
  }
  return out;
}

/** True when any node (at any depth) is a link. */
export function hasLink(nodes: readonly CvInline[]): boolean {
  return nodes.some(
    (node) => node.kind === "link" || ((node.kind === "strong" || node.kind === "em") && hasLink(node.children)),
  );
}

/** Splits inline nodes into lines on top-level line breaks. */
export function splitLines(nodes: readonly CvInline[]): CvInline[][] {
  const lines: CvInline[][] = [];
  let current: CvInline[] = [];
  for (const node of nodes) {
    if (node.kind === "break") {
      lines.push(current);
      current = [];
    } else {
      current.push(node);
    }
  }
  lines.push(current);
  return lines;
}

/** Joins lines back with line breaks (inverse of `splitLines`). */
export function joinLines(lines: readonly (readonly CvInline[])[]): CvInline[] {
  const out: CvInline[] = [];
  lines.forEach((line, index) => {
    if (index > 0) out.push({ kind: "break" });
    out.push(...line);
  });
  return out;
}

/** Drops whitespace at both ends of a line (only whitespace, never text). */
export function trimInlines(nodes: readonly CvInline[]): CvInline[] {
  const out = [...nodes];
  const first = out[0];
  if (first?.kind === "text") {
    const text = first.text.trimStart();
    if (text === "") out.shift();
    else out[0] = { kind: "text", text };
  }
  const lastIndex = out.length - 1;
  const last = out[lastIndex];
  if (last?.kind === "text") {
    // trimEnd, not /\s+$/: that regex is quadratic on a long run of spaces
    const text = last.text.trimEnd();
    if (text === "") out.pop();
    else out[lastIndex] = { kind: "text", text };
  }
  return out;
}

/** " · ", " | " and " • " between contacts (spaces on both sides, so "a|b" stays one part). */
// `(?<!\s)`: start only at the first space of a run, so a long run of spaces
// is scanned once, not once per space (quadratic on a 20 000-char line).
const CONTACT_SEPARATOR = /(?<!\s)\s+[·|•]\s+/u;

/**
 * Splits a line into parts on contact separators found in top-level text
 * (never inside a link or bold run). The separators themselves are dropped;
 * the renderer joins parts with its own " · ".
 */
export function splitOnSeparators(nodes: readonly CvInline[]): CvInline[][] {
  const parts: CvInline[][] = [];
  let current: CvInline[] = [];
  for (const node of nodes) {
    if (node.kind !== "text") {
      current.push(node);
      continue;
    }
    node.text.split(CONTACT_SEPARATOR).forEach((piece, index) => {
      if (index > 0) {
        parts.push(current);
        current = [];
      }
      if (piece !== "") current.push({ kind: "text", text: piece });
    });
  }
  parts.push(current);
  return parts.map(trimInlines).filter((part) => part.length > 0);
}

/** True when the top-level text holds a contact separator. */
export function hasSeparator(nodes: readonly CvInline[]): boolean {
  return nodes.some((node) => node.kind === "text" && CONTACT_SEPARATOR.test(node.text));
}
