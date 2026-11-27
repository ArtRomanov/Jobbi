import { useMemo } from "react";
import { colors } from "@/shared/ui";
import { buildSectionDiff } from "../lib/build-section-diff";
import { DiffLinesView } from "./diff-lines-view";

interface WholeCvDiffProps {
  beforeText: string;
  afterText: string;
}

/**
 * The body of a whole-CV card (`replace_all`): one diff per changed, added or
 * removed `## ` section, and the unchanged sections collapsed at the end.
 */
export function WholeCvDiff({ beforeText, afterText }: WholeCvDiffProps) {
  const sections = useMemo(
    () => buildSectionDiff(beforeText, afterText),
    [beforeText, afterText],
  );
  const changed = sections.filter((s) => s.kind !== "unchanged");
  const unchanged = sections.filter((s) => s.kind === "unchanged");

  return (
    <>
      {changed.length === 0 && (
        <p style={{ margin: 0, color: colors.textMuted }}>No changes to the CV text.</p>
      )}
      {changed.map((section, index) => (
        // Section titles may repeat; the order is fixed per card.
        <DiffLinesView
          key={index}
          label={`${section.title} — ${section.kind}`}
          rows={section.rows}
        />
      ))}
      {unchanged.length > 0 && (
        <details>
          <summary
            style={{ cursor: "pointer", color: colors.textMuted, fontSize: "0.75rem" }}
          >
            {`Unchanged sections (${unchanged.length}): ${unchanged
              .map((s) => s.title)
              .join(", ")}`}
          </summary>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "0.5rem",
              marginTop: "0.5rem",
            }}
          >
            {unchanged.map((section, index) => (
              <DiffLinesView key={index} label={section.title} rows={section.rows} />
            ))}
          </div>
        </details>
      )}
    </>
  );
}
