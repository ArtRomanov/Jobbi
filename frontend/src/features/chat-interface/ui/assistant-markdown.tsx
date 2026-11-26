import { createElement, memo, useMemo, type ReactNode } from "react";
import { Lexer } from "marked";
import type { Token, Tokens } from "marked";
import { isSafeCvLinkUrl } from "@/shared/lib";
import { VisuallyHidden } from "@/shared/ui";
import {
  BLOCK_STYLE,
  CODE_BLOCK_STYLE,
  HEADING_FONT_SIZES,
  HEADING_TAGS,
  INLINE_CODE_STYLE,
  LIST_STYLE,
  NEW_TAB_SUFFIX,
  QUOTE_STYLE,
  RAW_STYLE,
  ROOT_STYLE,
  RULE_STYLE,
  type MarkdownDepth,
} from "../lib/chat-markdown-styles";

interface AssistantMarkdownProps {
  /** Model output: untrusted. Rendered only as React elements, never as HTML. */
  content: string;
  /** Appended inside the last paragraph/heading (e.g. the streaming cursor). */
  trailing?: ReactNode;
}

// `breaks`: a single newline in a reply stays a line break.
const LEXER_OPTIONS = { gfm: true, breaks: true } as const;

function toDepth(depth: number): MarkdownDepth {
  return Math.min(Math.max(depth, 1), 6) as MarkdownDepth;
}

function renderInlines(tokens: readonly Token[] | undefined): ReactNode[] {
  if (!tokens) return [];
  return tokens.map((token, index) => {
    switch (token.type) {
      case "text": {
        const text = token as Tokens.Text;
        return text.tokens && text.tokens.length > 0 ? renderInlines(text.tokens) : text.text;
      }
      case "escape":
        return (token as Tokens.Escape).text;
      case "strong":
        return <strong key={index}>{renderInlines((token as Tokens.Strong).tokens)}</strong>;
      case "em":
        return <em key={index}>{renderInlines((token as Tokens.Em).tokens)}</em>;
      case "del":
        return <del key={index}>{renderInlines((token as Tokens.Del).tokens)}</del>;
      case "codespan":
        return (
          <code key={index} style={INLINE_CODE_STYLE}>
            {(token as Tokens.Codespan).text}
          </code>
        );
      case "br":
        return <br key={index} />;
      case "link": {
        const link = token as Tokens.Link;
        if (!isSafeCvLinkUrl(link.href)) return link.raw;
        return (
          <a key={index} href={link.href} target="_blank" rel="noopener noreferrer">
            {renderInlines(link.tokens)}
            <VisuallyHidden>{NEW_TAB_SUFFIX}</VisuallyHidden>
          </a>
        );
      }
      default:
        // Inline html, images, …: plain text exactly as the model wrote it.
        return token.raw;
    }
  });
}

/** Block-level "text" tokens (tight list items) carry inline tokens of their own. */
function renderTextBlock(token: Tokens.Text): ReactNode[] {
  return token.tokens ? renderInlines(token.tokens) : [token.text];
}

function renderBlocks(tokens: readonly Token[], trailing?: ReactNode): ReactNode[] {
  const visible = tokens.filter((token) => token.type !== "space" && token.type !== "def");
  const lastIndex = visible.length - 1;
  const out = visible.map((token, index) => {
    const tail = index === lastIndex ? trailing : null;
    switch (token.type) {
      case "heading": {
        const heading = token as Tokens.Heading;
        const depth = toDepth(heading.depth);
        return createElement(
          HEADING_TAGS[depth],
          { key: index, style: { ...BLOCK_STYLE, fontSize: HEADING_FONT_SIZES[depth], fontWeight: 600 } },
          ...renderInlines(heading.tokens),
          tail,
        );
      }
      case "paragraph":
        return (
          <p key={index} style={BLOCK_STYLE}>
            {renderInlines((token as Tokens.Paragraph).tokens)}
            {tail}
          </p>
        );
      case "text":
        return (
          <span key={index}>
            {renderTextBlock(token as Tokens.Text)}
            {tail}
          </span>
        );
      case "list": {
        const list = token as Tokens.List;
        const items = list.items.map((item, itemIndex) => (
          <li key={itemIndex}>{renderBlocks(item.tokens)}</li>
        ));
        return list.ordered ? (
          <ol key={index} start={typeof list.start === "number" ? list.start : undefined} style={LIST_STYLE}>
            {items}
          </ol>
        ) : (
          <ul key={index} style={LIST_STYLE}>
            {items}
          </ul>
        );
      }
      case "blockquote":
        return (
          <blockquote key={index} style={QUOTE_STYLE}>
            {renderBlocks((token as Tokens.Blockquote).tokens)}
          </blockquote>
        );
      case "code":
        return (
          <pre key={index} style={CODE_BLOCK_STYLE}>
            <code>{(token as Tokens.Code).text}</code>
          </pre>
        );
      case "hr":
        return <hr key={index} style={RULE_STYLE} />;
      default:
        // html, table, …: shown exactly as typed, never interpreted.
        return (
          <p key={index} style={RAW_STYLE}>
            {token.raw.replace(/\n+$/, "")}
          </p>
        );
    }
  });
  const last = visible[lastIndex];
  const tookTrailing = last?.type === "heading" || last?.type === "paragraph" || last?.type === "text";
  if (trailing && !tookTrailing) out.push(<span key="trailing">{trailing}</span>);
  return out;
}

/**
 * Renders an assistant reply's Markdown as React elements (marked tokens →
 * elements; no HTML string is ever built). Partial Markdown while streaming
 * just lexes as plain text until it closes.
 */
export const AssistantMarkdown = memo(function AssistantMarkdown({ content, trailing }: AssistantMarkdownProps) {
  const tokens = useMemo(() => new Lexer(LEXER_OPTIONS).lex(content), [content]);
  return <div style={ROOT_STYLE}>{renderBlocks(tokens, trailing)}</div>;
});
