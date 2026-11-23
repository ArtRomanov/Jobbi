import { memo, useMemo, type CSSProperties, type ReactNode } from "react";
import { colors } from "@/shared/ui";
import { isSafeCvLinkUrl } from "@/shared/lib";
import { parseCvMarkdown, type CvBlock, type CvInline } from "../lib/cv-markdown";

interface CvTextPreviewProps {
  /** The CV text (simple Markdown, see functional spec "Formatting"). */
  content: string;
}

// The preview sits inside a page that owns the <h1>, so CV headings 1–3 are
// rendered one level lower (h2–h4) to keep the page outline valid.
const HEADING_TAGS = { 1: "h2", 2: "h3", 3: "h4" } as const;

const HEADING_STYLES: Record<1 | 2 | 3, CSSProperties> = {
  1: { fontSize: "1.5rem", margin: "0 0 0.5rem" },
  2: { fontSize: "1.15rem", margin: "1rem 0 0.4rem", color: colors.primary },
  3: { fontSize: "1rem", margin: "0.75rem 0 0.25rem" },
};

const PARAGRAPH_STYLE: CSSProperties = { margin: "0 0 0.5rem" };
const RAW_STYLE: CSSProperties = { margin: "0 0 0.5rem", whiteSpace: "pre-wrap" };
const LIST_STYLE: CSSProperties = { margin: "0 0 0.5rem", paddingLeft: "1.5rem" };
const ROOT_STYLE: CSSProperties = {
  color: colors.textPrimary,
  lineHeight: 1.5,
  overflowWrap: "anywhere",
};

function renderInlines(nodes: readonly CvInline[]): ReactNode[] {
  return nodes.map((node, index) => {
    switch (node.kind) {
      case "text":
        return node.text;
      case "break":
        return <br key={index} />;
      case "strong":
        return <strong key={index}>{renderInlines(node.children)}</strong>;
      case "em":
        return <em key={index}>{renderInlines(node.children)}</em>;
      case "link":
        // The walker already filtered links; checked again so this renderer
        // stays safe on its own.
        return isSafeCvLinkUrl(node.href) ? (
          <a key={index} href={node.href} target="_blank" rel="noopener noreferrer">
            {renderInlines(node.children)}
          </a>
        ) : (
          <span key={index}>{renderInlines(node.children)}</span>
        );
    }
  });
}

function renderBlocks(blocks: readonly CvBlock[]): ReactNode[] {
  return blocks.map((block, index) => {
    switch (block.kind) {
      case "heading": {
        const Tag = HEADING_TAGS[block.level];
        return (
          <Tag key={index} style={HEADING_STYLES[block.level]}>
            {renderInlines(block.children)}
          </Tag>
        );
      }
      case "paragraph":
        return (
          <p key={index} style={PARAGRAPH_STYLE}>
            {renderInlines(block.children)}
          </p>
        );
      case "raw":
        return (
          <p key={index} style={RAW_STYLE}>
            {block.text}
          </p>
        );
      case "list": {
        const items = block.items.map((item, itemIndex) => (
          <li key={itemIndex}>{renderBlocks(item.blocks)}</li>
        ));
        return block.ordered ? (
          <ol key={index} start={block.start} style={LIST_STYLE}>
            {items}
          </ol>
        ) : (
          <ul key={index} style={LIST_STYLE}>
            {items}
          </ul>
        );
      }
    }
  });
}

/**
 * Formatted, read-only view of a CV text. Built from the same block model as
 * the PDF (`parseCvMarkdown`), with React elements only — never raw HTML.
 * Only http(s) and mailto links are clickable; they open in a new tab.
 */
export const CvTextPreview = memo(function CvTextPreview({ content }: CvTextPreviewProps) {
  const blocks = useMemo(() => parseCvMarkdown(content), [content]);
  return <div style={ROOT_STYLE}>{renderBlocks(blocks)}</div>;
});
