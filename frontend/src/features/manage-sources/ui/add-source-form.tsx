import { useId, type FormEvent, type Ref } from "react";
import { Button, FormInput, colors } from "@/shared/ui";
import { SOURCE_INPUT_HINT, SOURCE_INPUT_LABEL, SOURCE_INPUT_PLACEHOLDER } from "../lib/constants";

interface AddSourceFormProps {
  value: string;
  error: string | null;
  /** A request runs: the input is read-only and "Add" shows loading. */
  isBusy: boolean;
  /** "Add" itself is the running request (shows loading rather than disabled). */
  isAdding: boolean;
  /** Blocks the whole form (e.g. until the source list has loaded). */
  isDisabled: boolean;
  inputRef: Ref<HTMLInputElement>;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

/**
 * Input + "Add" button; Enter submits. The inline error sits under the input,
 * followed by the always-visible "sort by newest" hint.
 */
export function AddSourceForm({
  value,
  error,
  isBusy,
  isAdding,
  isDisabled,
  inputRef,
  onChange,
  onSubmit,
}: AddSourceFormProps) {
  const inputId = useId();
  const hintId = useId();
  // FormInput only links its error; keep that link and add the hint
  const describedBy = error ? `${inputId}-error ${hintId}` : hintId;

  const handleSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    onSubmit();
  };

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem" }}
    >
      <div style={{ flex: 1 }}>
        <FormInput
          ref={inputRef}
          id={inputId}
          label={SOURCE_INPUT_LABEL}
          placeholder={SOURCE_INPUT_PLACEHOLDER}
          autoComplete="off"
          spellCheck={false}
          value={value}
          error={error ?? undefined}
          disabled={isDisabled}
          readOnly={isBusy}
          aria-describedby={describedBy}
          onChange={(event) => onChange(event.target.value)}
        />
        <p
          id={hintId}
          style={{
            margin: "-0.75rem 0 1rem",
            fontSize: "0.75rem",
            color: colors.textMuted,
          }}
        >
          {SOURCE_INPUT_HINT}
        </p>
      </div>
      <Button
        type="submit"
        loading={isAdding}
        disabled={isDisabled || isBusy || value.trim() === ""}
        style={{ marginTop: "1.5rem", flexShrink: 0 }}
      >
        Add
      </Button>
    </form>
  );
}
