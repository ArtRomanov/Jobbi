import { useId, useRef, type FormEvent } from "react";
import type { VacancySearchSettings } from "@/entities/vacancy-source";
import { Button, FormTextarea, colors } from "@/shared/ui";
import { DESCRIPTION_MAX_LENGTH, DESCRIPTION_PLACEHOLDER } from "../lib/constants";
import { useSearchSettingsForm } from "../model/use-search-settings-form";

interface SearchSettingsFormProps {
  /** Saved settings used as the initial drafts; null while loading (form disabled). */
  initialSettings: VacancySearchSettings | null;
  onSaved: (settings: VacancySearchSettings) => void;
}

/**
 * "What are you looking for?": search description (500 chars, live counter).
 * Re-mount it (via `key`) when the saved settings first load so the draft
 * starts from them.
 */
export function SearchSettingsForm({ initialSettings, onSaved }: SearchSettingsFormProps) {
  const headingId = useId();
  const counterId = useId();
  const saveButtonRef = useRef<HTMLButtonElement>(null);
  const { description, setDescription, saveError, isSaving, save } = useSearchSettingsForm(
    initialSettings,
    onSaved,
  );
  const isDisabled = initialSettings === null;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    if (isDisabled) return;
    await save();
    // The button is disabled while saving, which drops focus; put it back
    saveButtonRef.current?.focus();
  };

  return (
    <section aria-labelledby={headingId} style={{ marginTop: "1.5rem" }}>
      <h3
        id={headingId}
        style={{
          fontSize: "1rem",
          fontWeight: 600,
          marginBottom: "0.75rem",
          color: colors.textPrimary,
        }}
      >
        What are you looking for?
      </h3>
      <form onSubmit={(event) => void handleSubmit(event)} noValidate>
        <FormTextarea
          label="Search description"
          placeholder={DESCRIPTION_PLACEHOLDER}
          rows={3}
          maxLength={DESCRIPTION_MAX_LENGTH}
          value={description}
          disabled={isDisabled}
          readOnly={isSaving}
          aria-describedby={counterId}
          onChange={(event) => setDescription(event.target.value)}
        />
        <p
          id={counterId}
          style={{
            marginTop: "-0.75rem",
            marginBottom: "1rem",
            fontSize: "0.75rem",
            color: colors.textMuted,
            textAlign: "right",
          }}
        >
          {description.length}/{DESCRIPTION_MAX_LENGTH}
        </p>
        <Button ref={saveButtonRef} type="submit" loading={isSaving} disabled={isDisabled}>
          Save
        </Button>
        {saveError ? (
          <p
            role="alert"
            style={{ marginTop: "0.5rem", fontSize: "0.75rem", color: colors.error }}
          >
            {saveError}
          </p>
        ) : null}
      </form>
    </section>
  );
}
