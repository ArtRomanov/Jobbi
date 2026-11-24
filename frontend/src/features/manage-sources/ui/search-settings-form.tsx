import { useId, useRef, type FormEvent } from "react";
import type { VacancySearchSettings } from "@/entities/vacancy-source";
import { Button, ChipInput, FormTextarea, colors } from "@/shared/ui";
import {
  DESCRIPTION_MAX_LENGTH,
  DESCRIPTION_PLACEHOLDER,
  FILTERED_LAST_24H_PREFIX,
  KEYWORDS_HINT,
  KEYWORDS_LABEL,
  KEYWORDS_LIMIT_MESSAGE,
  KEYWORDS_MAX_COUNT,
  KEYWORDS_PLACEHOLDER,
  KEYWORD_MAX_LENGTH,
} from "../lib/constants";
import { useSearchSettingsForm } from "../model/use-search-settings-form";
import { KeywordFilterSwitch } from "./keyword-filter-switch";

interface SearchSettingsFormProps {
  /** Saved settings used as the initial drafts; null while loading (form disabled). */
  initialSettings: VacancySearchSettings | null;
  onSaved: (settings: VacancySearchSettings) => void;
  /** Posts the keyword filter skipped in the last 24 h (from status); null hides the line. */
  filteredLast24h: number | null;
}

/**
 * "What are you looking for?": search description (500 chars, live counter),
 * pre-AI keywords (chips) + the keyword-filter switch, and the "skipped in the
 * last 24 hours" counter. Save sends all three fields in one PATCH.
 * Re-mount it (via `key`) when the saved settings first load so the draft
 * starts from them.
 */
export function SearchSettingsForm({
  initialSettings,
  onSaved,
  filteredLast24h,
}: SearchSettingsFormProps) {
  const headingId = useId();
  const counterId = useId();
  const saveButtonRef = useRef<HTMLButtonElement>(null);
  const {
    description,
    setDescription,
    keywords,
    setKeywords,
    keywordFilter,
    setKeywordFilter,
    saveError,
    isSaving,
    save,
  } = useSearchSettingsForm(initialSettings, onSaved);
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
        <ChipInput
          label={KEYWORDS_LABEL}
          values={keywords}
          onChange={setKeywords}
          maxItems={KEYWORDS_MAX_COUNT}
          maxItemsMessage={KEYWORDS_LIMIT_MESSAGE}
          maxLength={KEYWORD_MAX_LENGTH}
          placeholder={KEYWORDS_PLACEHOLDER}
          hint={KEYWORDS_HINT}
          disabled={isDisabled || isSaving}
        />
        <KeywordFilterSwitch
          checked={keywordFilter}
          disabled={isDisabled || isSaving}
          onChange={setKeywordFilter}
        />
        {filteredLast24h !== null ? (
          <p style={{ margin: "0 0 1rem", fontSize: "0.75rem", color: colors.textSecondary }}>
            {FILTERED_LAST_24H_PREFIX} {filteredLast24h}
          </p>
        ) : null}
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
