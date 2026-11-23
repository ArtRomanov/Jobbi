import { VisuallyHidden } from "@/shared/ui";
import type { DiffRow } from "../lib/build-diff-rows";
import { DIFF_LINE_STYLE, DIFF_ROW_KIND } from "../lib/card-styles";

/** One diff line: `<del>` / `<ins>` / plain, with a −/+ marker and a screen-reader prefix. */
export function DiffLine({ row }: { row: DiffRow }) {
  const kind = DIFF_ROW_KIND[row.kind];
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
  const style = { ...DIFF_LINE_STYLE, ...kind.style };
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
