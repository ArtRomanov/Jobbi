import type { CSSProperties } from "react";
import { colors, fonts, VisuallyHidden } from "@/shared/ui";
import type { DiffRow, DiffRowKind } from "../lib/build-diff-rows";

interface DiffLinesViewProps {
  /** Visible caption, e.g. "Before", "After", "Removed", "Added at the end". */
  label: string;
  rows: DiffRow[];
}

/** Marker, screen-reader prefix and colours per line kind (readable without colour). */
const ROW_KIND: Record<
  DiffRowKind,
  { marker: string; srPrefix: string | null; style: CSSProperties }
> = {
  same: { marker: " ", srPrefix: null, style: { color: colors.textSecondary } },
  removed: {
    marker: "−",
    srPrefix: "Removed line: ",
    style: {
      backgroundColor: colors.badge.danger.bg,
      color: colors.badge.danger.text,
    },
  },
  added: {
    marker: "+",
    srPrefix: "Added line: ",
    style: {
      backgroundColor: colors.badge.success.bg,
      color: colors.badge.success.text,
    },
  },
};

const LINE_STYLE: CSSProperties = {
  display: "flex",
  gap: "0.5rem",
  padding: "0 0.375rem",
  textDecoration: "none",
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};

function DiffLine({ row }: { row: DiffRow }) {
  const kind = ROW_KIND[row.kind];
  const content = (
    <>
      <span aria-hidden="true" style={{ flexShrink: 0, fontWeight: 700 }}>
        {kind.marker}
      </span>
      <span>
        {kind.srPrefix ? <VisuallyHidden>{kind.srPrefix}</VisuallyHidden> : null}
        {/* Keep empty lines visible as a row */}
        {row.text === "" ? " " : row.text}
      </span>
    </>
  );
  const style = { ...LINE_STYLE, ...kind.style };
  if (row.kind === "removed") {
    return (
      <del data-diff="removed" style={style}>
        {content}
      </del>
    );
  }
  if (row.kind === "added") {
    return (
      <ins data-diff="added" style={style}>
        {content}
      </ins>
    );
  }
  return (
    <div data-diff="same" style={style}>
      {content}
    </div>
  );
}

/** One column of a change card: a caption and its lines with −/+ markers. */
export function DiffLinesView({ label, rows }: DiffLinesViewProps) {
  return (
    <div style={{ minWidth: 0 }}>
      <div
        style={{
          fontSize: "0.75rem",
          fontWeight: 600,
          color: colors.textMuted,
          marginBottom: "0.25rem",
        }}
      >
        {label}
      </div>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          fontFamily: fonts.base,
          fontSize: "0.8125rem",
          lineHeight: 1.5,
          border: `1px solid ${colors.borderLight}`,
          borderRadius: "0.375rem",
          padding: "0.25rem 0",
          backgroundColor: colors.bgCard,
        }}
      >
        {rows.map((row, index) => (
          // Lines have no identity of their own; order is fixed per card.
          <DiffLine key={index} row={row} />
        ))}
      </div>
    </div>
  );
}
