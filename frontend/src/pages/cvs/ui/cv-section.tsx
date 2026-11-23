import { useId, type ReactNode } from "react";
import { colors } from "@/shared/ui";

interface CvSectionProps {
  title: string;
  children: ReactNode;
}

/** A titled group of CVs on the CVs page ("My CVs", "Tailored for applications"). */
export function CvSection({ title, children }: CvSectionProps) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} style={{ marginTop: "1.5rem" }}>
      <h2
        id={headingId}
        style={{ fontSize: "1rem", fontWeight: 700, margin: "0 0 0.5rem", color: colors.textPrimary }}
      >
        {title}
      </h2>
      {children}
    </section>
  );
}
