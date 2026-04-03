import { colors } from "./theme";

interface DividerProps {
  label?: string;
}

/**
 * Horizontal rule with an optional descriptive label below it.
 * Used to separate form sections (e.g. required vs optional fields).
 */
export function Divider({ label }: DividerProps) {
  return (
    <>
      <hr
        style={{
          border: "none",
          borderTop: `1px solid ${colors.borderLight}`,
          margin: "1.5rem 0",
        }}
      />
      {label ? (
        <p
          style={{
            fontSize: "0.75rem",
            color: colors.textPlaceholder,
            marginBottom: "1rem",
          }}
        >
          {label}
        </p>
      ) : null}
    </>
  );
}
