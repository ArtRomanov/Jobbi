import type { FormEvent, Ref } from "react";
import { Button, FormInput } from "@/shared/ui";
import { SOURCE_INPUT_PLACEHOLDER } from "../lib/constants";

interface AddSourceFormProps {
  value: string;
  error: string | null;
  isAdding: boolean;
  /** Blocks the whole form (e.g. until the source list has loaded). */
  isDisabled: boolean;
  inputRef: Ref<HTMLInputElement>;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

/** Input + "Add" button; Enter submits. The inline error sits under the input. */
export function AddSourceForm({
  value,
  error,
  isAdding,
  isDisabled,
  inputRef,
  onChange,
  onSubmit,
}: AddSourceFormProps) {
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
          label="Add a Telegram channel"
          placeholder={SOURCE_INPUT_PLACEHOLDER}
          autoComplete="off"
          spellCheck={false}
          value={value}
          error={error ?? undefined}
          disabled={isDisabled}
          readOnly={isAdding}
          onChange={(event) => onChange(event.target.value)}
        />
      </div>
      <Button
        type="submit"
        loading={isAdding}
        disabled={isDisabled || value.trim() === ""}
        style={{ marginTop: "1.5rem", flexShrink: 0 }}
      >
        Add
      </Button>
    </form>
  );
}
