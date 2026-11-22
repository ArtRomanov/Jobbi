import type { Ref } from "react";
import { colors } from "./theme";

interface PageHeaderProps {
  title: string;
  subtitle: string;
  /** Lets the page move focus to the title (it becomes focusable by script only). */
  titleRef?: Ref<HTMLHeadingElement>;
}

/**
 * Page-level heading with a title (h1) and subtitle paragraph.
 * Used consistently across auth and authenticated pages.
 */
export function PageHeader({ title, subtitle, titleRef }: PageHeaderProps) {
  return (
    <>
      <h1
        ref={titleRef}
        tabIndex={titleRef ? -1 : undefined}
        style={{
          fontSize: "1.5rem",
          fontWeight: 700,
          marginBottom: "0.25rem",
          color: colors.textPrimary,
        }}
      >
        {title}
      </h1>
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
