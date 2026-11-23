import { useDeferredValue } from "react";
import { CvTextPreview } from "@/entities/cv";
import { colors } from "@/shared/ui";

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
    <section
      aria-label="Preview"
      style={{
        padding: "1rem",
        border: `1px solid ${colors.borderLight}`,
        borderRadius: "0.375rem",
        minHeight: "12rem",
        overflow: "auto",
      }}
    >
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
