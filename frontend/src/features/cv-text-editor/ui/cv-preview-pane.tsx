import { useDeferredValue } from "react";
import { CvTextPreview } from "@/entities/cv";
import { colors } from "@/shared/ui";
import { CV_PANE_BOX_STYLE } from "../config";

interface CvPreviewPaneProps {
  content: string;
}

/**
 * Live preview of the CV text. `useDeferredValue` lets typing stay responsive
 * on long CVs: React re-parses the Markdown at a lower priority.
 */
export function CvPreviewPane({ content }: CvPreviewPaneProps) {
  const deferredContent = useDeferredValue(content);

  return (
    // A scrollable region must be reachable by keyboard: tabIndex 0 lets the
    // user focus it and scroll with the arrow keys
    <section role="region" aria-label="CV preview" tabIndex={0} style={CV_PANE_BOX_STYLE}>
      {deferredContent.trim() ? (
        <CvTextPreview content={deferredContent} />
      ) : (
        <p style={{ margin: 0, fontSize: "0.875rem", color: colors.textMuted }}>
          Nothing to preview yet.
        </p>
      )}
    </section>
  );
}
