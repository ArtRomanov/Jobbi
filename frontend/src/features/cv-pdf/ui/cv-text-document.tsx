import type { ReactNode } from "react";
import { Document, Link, Page, StyleSheet, Text, View } from "@react-pdf/renderer";
import { parseCvMarkdown, type CvBlock, type CvInline } from "@/entities/cv";
import { isSafeCvLinkUrl } from "@/shared/lib";
import { colors } from "@/shared/ui";
import { CV_PDF_FONT_FAMILY } from "../lib/register-cv-fonts";

export interface CvTextDocumentProps {
  name: string;
  content: string;
}

const styles = StyleSheet.create({
  page: {
    paddingVertical: 40,
    paddingHorizontal: 44,
    fontFamily: CV_PDF_FONT_FAMILY,
    fontSize: 10,
    lineHeight: 1.4,
    color: colors.textPrimary,
  },
  heading1: { fontSize: 20, fontWeight: 700, marginBottom: 6 },
  heading2: {
    fontSize: 13,
    fontWeight: 700,
    color: colors.primary,
    marginTop: 12,
    marginBottom: 4,
  },
  heading3: { fontSize: 11, fontWeight: 700, marginTop: 8, marginBottom: 2 },
  heading4: { fontSize: 10, fontWeight: 700, marginTop: 6, marginBottom: 2 },
  paragraph: { marginBottom: 5 },
  list: { marginBottom: 5 },
  listItem: { flexDirection: "row" },
  listMarker: { width: 16 },
  listContent: { flex: 1 },
  listParagraph: { marginBottom: 1 },
  strong: { fontWeight: 700 },
  em: { fontStyle: "italic" },
  link: { color: colors.primary, textDecoration: "none" },
});

const HEADING_STYLES = {
  1: styles.heading1,
  2: styles.heading2,
  3: styles.heading3,
  4: styles.heading4,
} as const;

// Keep a heading together with the start of the text that follows it instead
// of leaving it alone at the bottom of a page.
const HEADING_MIN_PRESENCE_AHEAD = 36;

function renderInlines(nodes: readonly CvInline[]): ReactNode[] {
  return nodes.map((node, index) => {
    switch (node.kind) {
      case "text":
        return node.text;
      case "break":
        return "\n";
      case "strong":
        return (
          <Text key={index} style={styles.strong}>
            {renderInlines(node.children)}
          </Text>
        );
      case "em":
        return (
          <Text key={index} style={styles.em}>
            {renderInlines(node.children)}
          </Text>
        );
      case "link":
        // Same model as the preview; re-checked so this renderer is safe alone.
        return isSafeCvLinkUrl(node.href) ? (
          <Link key={index} src={node.href} style={styles.link}>
            {renderInlines(node.children)}
          </Link>
        ) : (
          <Text key={index}>{renderInlines(node.children)}</Text>
        );
    }
  });
}

function renderBlocks(blocks: readonly CvBlock[], isInList = false): ReactNode[] {
  return blocks.map((block, index) => {
    switch (block.kind) {
      case "heading":
        return (
          <Text
            key={index}
            style={HEADING_STYLES[block.level]}
            minPresenceAhead={HEADING_MIN_PRESENCE_AHEAD}
          >
            {renderInlines(block.children)}
          </Text>
        );
      case "paragraph":
        return (
          <Text key={index} style={isInList ? styles.listParagraph : styles.paragraph}>
            {renderInlines(block.children)}
          </Text>
        );
      case "raw":
        return (
          <Text key={index} style={isInList ? styles.listParagraph : styles.paragraph}>
            {block.text}
          </Text>
        );
      case "list":
        return (
          <View key={index} style={styles.list}>
            {block.items.map((item, itemIndex) => (
              <View key={itemIndex} style={styles.listItem}>
                <Text style={styles.listMarker}>
                  {block.ordered ? `${block.start + itemIndex}.` : "•"}
                </Text>
                <View style={styles.listContent}>{renderBlocks(item.blocks, true)}</View>
              </View>
            ))}
          </View>
        );
    }
  });
}

/**
 * The CV PDF: the whole CV text, formatted like the preview (same block model
 * from `parseCvMarkdown`), on A4 pages that break automatically. The CV name is
 * printed only when the text is empty (functional spec 2.8). Fonts must be
 * registered first (`registerCvFonts`).
 */
export function CvTextDocument({ name, content }: CvTextDocumentProps) {
  const blocks = parseCvMarkdown(content);
  return (
    <Document title={name}>
      <Page size="A4" style={styles.page}>
        {blocks.length === 0 ? <Text style={styles.heading1}>{name}</Text> : renderBlocks(blocks)}
      </Page>
    </Document>
  );
}
