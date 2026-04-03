import { forwardRef, useId, type SelectHTMLAttributes } from "react";
import { colors } from "./theme";

interface SelectOption {
  value: string;
  label: string;
}

interface FormSelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  options: SelectOption[];
  error?: string;
}

/**
 * Reusable styled select with label and error display.
 * Accepts React Hook Form register spread via forwardRef.
 */
export const FormSelect = forwardRef<HTMLSelectElement, FormSelectProps>(
  function FormSelect({ label, options, error, id: providedId, ...rest }, ref) {
    const generatedId = useId();
    const id = providedId ?? generatedId;
    const errorId = `${id}-error`;

    return (
      <div style={{ marginBottom: "1rem" }}>
        <label
          htmlFor={id}
          style={{
            display: "block",
            marginBottom: "0.25rem",
            fontSize: "0.875rem",
            fontWeight: 500,
            color: colors.textSecondary,
          }}
        >
          {label}
        </label>
        <select
          ref={ref}
          id={id}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          style={{
            width: "100%",
            padding: "0.5rem 0.75rem",
            border: `1px solid ${error ? colors.error : colors.border}`,
            borderRadius: "0.375rem",
            fontSize: "0.875rem",
            backgroundColor: colors.bgCard,
            boxSizing: "border-box",
          }}
          {...rest}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {error ? (
          <p
            id={errorId}
            role="alert"
            style={{
              marginTop: "0.25rem",
              fontSize: "0.75rem",
              color: colors.error,
            }}
          >
            {error}
          </p>
        ) : null}
      </div>
    );
  },
);
