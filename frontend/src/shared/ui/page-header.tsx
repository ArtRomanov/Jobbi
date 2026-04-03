import { colors } from "./theme";

interface PageHeaderProps {
  title: string;
  subtitle: string;
}

/**
 * Page-level heading with a title (h1) and subtitle paragraph.
 * Used consistently across auth and authenticated pages.
 */
export function PageHeader({ title, subtitle }: PageHeaderProps) {
  return (
    <>
      <h1
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
