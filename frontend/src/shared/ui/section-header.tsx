import type { Ref } from "react";
import { colors } from "./theme";

interface SectionHeaderProps {
  title: string;
  subtitle: string;
  /** Optional heading id so a wrapping <section> can use aria-labelledby. */
  id?: string;
  /** When given, the heading becomes programmatically focusable (tabIndex=-1). */
  headingRef?: Ref<HTMLHeadingElement>;
}

/**
 * Secondary section heading (h2 + subtitle) preceded by a separator rule.
 * Used for stacked sections inside a single PageCard (e.g. Settings).
 */
export function SectionHeader({ title, subtitle, id, headingRef }: SectionHeaderProps) {
  return (
    <>
      <hr
        style={{
          border: "none",
          borderTop: `1px solid ${colors.borderLight}`,
          margin: "2rem 0",
        }}
      />
      <h2
        id={id}
        ref={headingRef}
        tabIndex={headingRef ? -1 : undefined}
        style={{
          fontSize: "1.25rem",
          fontWeight: 700,
          marginBottom: "0.25rem",
          color: colors.textPrimary,
        }}
      >
        {title}
      </h2>
      <p
        style={{
          fontSize: "0.875rem",
          color: colors.textMuted,
          marginBottom: "1.5rem",
        }}
      >
        {subtitle}
      </p>
    </>
  );
}
