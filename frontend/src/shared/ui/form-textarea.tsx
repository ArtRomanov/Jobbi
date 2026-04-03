import { forwardRef, useId, type TextareaHTMLAttributes } from "react";
import { colors } from "./theme";

interface FormTextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  error?: string;
}

/**
 * Reusable styled textarea with label and error display.
 * Accepts React Hook Form register spread via forwardRef.
 */
export const FormTextarea = forwardRef<HTMLTextAreaElement, FormTextareaProps>(
  function FormTextarea({ label, error, id: providedId, ...rest }, ref) {
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
        <textarea
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
            resize: "vertical",
            boxSizing: "border-box",
            fontFamily: "inherit",
          }}
          {...rest}
        />
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
