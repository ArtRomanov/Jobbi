import { colors, fonts } from "@/shared/ui";
import type { DiffRow } from "../lib/build-diff-rows";
import { DiffLine } from "./diff-line";

interface DiffLinesViewProps {
  /** Visible caption, e.g. "Before", "After", "Removed", "Added at the end". */
  label: string;
  rows: DiffRow[];
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
