import { Fragment, type ReactNode } from "react";
import { isSafeCvLinkUrl } from "@/shared/lib";
import { VisuallyHidden } from "@/shared/ui";
import { NEW_TAB_SUFFIX } from "../lib/constants";
import type { CvBlock, CvInline } from "../lib/cv-markdown";
import type { CvLayout, CvLayoutBlock, CvLayoutEntry, CvLayoutItem } from "../lib/cv-layout";
import { CV_LAYOUT_CLASSES as C } from "../lib/cv-layout-styles";

export interface CvLayoutViewProps {
  layout: CvLayout;
  /**
   * Inside an app page (the editor preview): the page owns the `<h1>`, so
   * headings go one level lower, and links open a new tab. Off for the
   * standalone document ("Download HTML"): `h1` name, plain links.
   */
  isEmbedded: boolean;
}

type HeadingTag = "h1" | "h2" | "h3" | "h4";

interface RenderContext {
  isEmbedded: boolean;
}

const STANDALONE_TAGS = { 1: "h1", 2: "h2", 3: "h3" } as const satisfies Record<1 | 2 | 3, HeadingTag>;
const EMBEDDED_TAGS = { 1: "h2", 2: "h3", 3: "h4" } as const satisfies Record<1 | 2 | 3, HeadingTag>;

function headingTag(level: 1 | 2 | 3, ctx: RenderContext): HeadingTag {
  return (ctx.isEmbedded ? EMBEDDED_TAGS : STANDALONE_TAGS)[level];
}

function renderInlines(nodes: readonly CvInline[], ctx: RenderContext): ReactNode[] {
  return nodes.map((node, index) => {
    switch (node.kind) {
      case "text":
        return node.text;
      case "break":
        return <br key={index} />;
      case "strong":
        return <strong key={index}>{renderInlines(node.children, ctx)}</strong>;
      case "em":
        return <em key={index}>{renderInlines(node.children, ctx)}</em>;
      case "link":
        // The parser already filtered links; checked again so this renderer
        // stays safe on its own (it also feeds the downloaded HTML).
        if (!isSafeCvLinkUrl(node.href)) {
          return <span key={index}>{renderInlines(node.children, ctx)}</span>;
        }
        return ctx.isEmbedded ? (
          <a key={index} href={node.href} target="_blank" rel="noopener noreferrer">
            {renderInlines(node.children, ctx)}
            <VisuallyHidden>{NEW_TAB_SUFFIX}</VisuallyHidden>
          </a>
        ) : (
          <a key={index} href={node.href} rel="noopener noreferrer">
            {renderInlines(node.children, ctx)}
          </a>
        );
    }
  });
}

/** Blocks inside list items (any `CvBlock`, headings included). */
function renderNestedBlock(block: CvBlock, key: number, ctx: RenderContext): ReactNode {
  switch (block.kind) {
    case "heading":
      return (
        <p key={key} className={C.subheading}>
          {renderInlines(block.children, ctx)}
        </p>
      );
    case "paragraph":
      return renderLayoutBlock({ ...block, isContext: false }, key, ctx);
    case "list":
    case "raw":
      return renderLayoutBlock(block, key, ctx);
  }
}

function renderLayoutBlock(block: CvLayoutBlock, key: number, ctx: RenderContext): ReactNode {
  switch (block.kind) {
    case "paragraph":
      return (
        <p key={key} className={block.isContext ? `${C.paragraph} ${C.context}` : C.paragraph}>
          {renderInlines(block.children, ctx)}
        </p>
      );
    case "raw":
      return (
        <p key={key} className={C.raw}>
          {block.text}
        </p>
      );
    case "list": {
      const items = block.items.map((item, itemIndex) => (
        <li key={itemIndex}>{item.blocks.map((nested, i) => renderNestedBlock(nested, i, ctx))}</li>
      ));
      return block.ordered ? (
        <ol key={key} start={block.start} className={`${C.list} ${C.orderedList}`}>
          {items}
        </ol>
      ) : (
        <ul key={key} className={C.list}>
          {items}
        </ul>
      );
    }
  }
}

function renderEntry(entry: CvLayoutEntry, key: number, ctx: RenderContext): ReactNode {
  const TitleTag = headingTag(3, ctx);
  const [first, ...rest] = entry.blocks;
  // Title row + a short first paragraph stay on one page; a list may break
  const keepFirst = first?.kind === "paragraph";
  const head = (
    <div className={C.entryHead}>
      <TitleTag className={C.entryTitle}>{renderInlines(entry.title, ctx)}</TitleTag>
      {entry.dates ? (
        <span className={C.entryDates}>
          {/* Keeps title and dates apart in the text ("Engineer · Jan", not "EngineerJan") */}
          {entry.datesSeparator ? <span className={C.visuallyHidden}>{entry.datesSeparator}</span> : null}
          {renderInlines(entry.dates, ctx)}
        </span>
      ) : null}
    </div>
  );
  return (
    <div key={key} className={C.entry}>
      <div className={C.entryLead}>
        {head}
        {keepFirst ? renderLayoutBlock(first, 0, ctx) : null}
      </div>
      {(keepFirst ? rest : entry.blocks).map((block, i) => renderLayoutBlock(block, i + 1, ctx))}
    </div>
  );
}

function renderItem(item: CvLayoutItem, key: number, ctx: RenderContext): ReactNode {
  return item.kind === "entry" ? renderEntry(item, key, ctx) : renderLayoutBlock(item, key, ctx);
}

/**
 * The designed CV (backlog #11) from a `CvLayout`: React elements only, so all
 * CV text is escaped by React (also when rendered to static HTML for the
 * download). Styled by `CV_LAYOUT_CSS`, which the caller puts on the page.
 */
export function CvLayoutView({ layout, isEmbedded }: CvLayoutViewProps) {
  const ctx: RenderContext = { isEmbedded };
  const { header } = layout;
  const NameTag = headingTag(1, ctx);
  const SectionTag = headingTag(2, ctx);
  return (
    <div className={C.root}>
      {header ? (
        <header className={C.header}>
          <NameTag className={C.name}>{renderInlines(header.name, ctx)}</NameTag>
          {header.title ? <p className={C.title}>{renderInlines(header.title, ctx)}</p> : null}
          <div className={C.rule} aria-hidden="true" />
          {header.contacts.length > 0 ? (
            <p className={C.contacts}>
              {header.contacts.map((part, index) => (
                <Fragment key={index}>
                  {index > 0 ? <span className={C.separator}>{" · "}</span> : null}
                  <span>{renderInlines(part, ctx)}</span>
                </Fragment>
              ))}
            </p>
          ) : null}
        </header>
      ) : null}
      {layout.sections.map((section, sectionIndex) => (
        <section key={sectionIndex} className={C.section}>
          {section.heading ? (
            <SectionTag className={C.sectionHeading}>{renderInlines(section.heading, ctx)}</SectionTag>
          ) : null}
          {section.items.map((item, i) => renderItem(item, i, ctx))}
        </section>
      ))}
    </div>
  );
}
