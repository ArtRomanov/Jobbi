import type { ReactNode, Ref } from "react";
import { colors } from "./theme";

interface SectionHeaderProps {
  title: string;
  subtitle?: string;
  /** Optional heading id so a wrapping <section> can use aria-labelledby. */
  id?: string;
  /** When given, the heading becomes programmatically focusable (tabIndex=-1). */
  headingRef?: Ref<HTMLHeadingElement>;
  /** Separator rule above the heading (default true). */
  hasDivider?: boolean;
  /** Control shown at the end of the heading row (e.g. a `SectionToggle`). */
  action?: ReactNode;
}

/**
 * Secondary section heading (h2 + optional subtitle), by default preceded by a
 * separator rule. Used for stacked sections inside a single PageCard (e.g. Settings).
 */
export function SectionHeader({
  title,
  subtitle,
  id,
  headingRef,
  hasDivider = true,
  action,
}: SectionHeaderProps) {
  const heading = (
    <h2
      id={id}
      ref={headingRef}
      tabIndex={headingRef ? -1 : undefined}
      style={{
        fontSize: "1.25rem",
        fontWeight: 700,
        marginBottom: subtitle ? "0.25rem" : "1rem",
        color: colors.textPrimary,
      }}
    >
      {title}
    </h2>
  );

  return (
    <>
      {hasDivider ? (
        <hr
          style={{
            border: "none",
            borderTop: `1px solid ${colors.borderLight}`,
            margin: "2rem 0",
          }}
        />
      ) : null}
      {action ? (
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "1rem" }}>
          {heading}
          {action}
        </div>
      ) : (
        heading
      )}
      {subtitle ? (
        <p
          style={{
            fontSize: "0.875rem",
            color: colors.textMuted,
            marginBottom: "1.5rem",
          }}
        >
          {subtitle}
        </p>
      ) : null}
    </>
  );
}
