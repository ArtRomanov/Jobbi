import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import type { VacancySourcePreview } from "@/entities/vacancy-source";
import { Button, FormInput, colors } from "@/shared/ui";
import {
  JOB_LINK_CONTAINS_LABEL,
  JOB_LINK_CONTAINS_MAX_LENGTH,
  JOB_LINK_CONTAINS_PLACEHOLDER,
  PREVIEW_NO_VACANCIES_TEXT,
  PREVIEW_TITLES_LIMIT,
  SOURCE_NAME_LABEL,
  SOURCE_NAME_MAX_LENGTH,
} from "../lib/constants";
import { formatFoundCount } from "../lib/helpers";
import { toFieldErrors, webSourceOptionsSchema, type WebSourceOptions } from "../model/schemas";
import type { WebSourceFieldErrors } from "../model/types";
import { AtsHint } from "./ats-hint";

interface SourcePreviewProps {
  result: VacancySourcePreview;
  initialJobLinkContains?: string;
  initialName?: string;
  /** A request (re-check or save) is running: fields read-only, buttons blocked. */
  busy: boolean;
  /** Which button shows loading while `busy`. */
  busyAction?: "recheck" | "save" | "board" | null;
  /** Re-check / save error from the server, shown at the bottom. */
  error: string | null;
  /** Focus the heading on mount (the add flow); a dialog may manage focus itself. */
  focusOnMount?: boolean;
  /** May return a promise; focus goes back to Re-check when it settles. */
  onRecheck: (jobLinkContains: string | null) => void | Promise<void>;
  /** May resolve to success; on `false` focus goes back to Save. */
  onSave: (options: WebSourceOptions) => void | Promise<boolean>;
  onCancel: () => void;
  /** Adds the board from `result.ats_hint`; without it the hint is not shown. */
  onAddBoard?: (boardInput: string) => Promise<boolean>;
}

/**
 * Preview of a web page source before it is saved: "Found N vacancies", the
 * first titles in site order (or a muted "No vacancies found…" line when the
 * page has no job links but links to an ATS board; Save is then disabled), "Job link contains" with Re-check, an optional
 * name (placeholder = default name) and Save / Cancel. Shared by add and edit.
 */
export function SourcePreview({
  result,
  initialJobLinkContains = "",
  initialName = "",
  busy,
  busyAction = null,
  error,
  focusOnMount = true,
  onRecheck,
  onSave,
  onCancel,
  onAddBoard,
}: SourcePreviewProps) {
  const headingId = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const recheckButtonRef = useRef<HTMLButtonElement>(null);
  const saveButtonRef = useRef<HTMLButtonElement>(null);
  const [jobLinkContains, setJobLinkContains] = useState(initialJobLinkContains);
  const [name, setName] = useState(initialName);
  const [fieldErrors, setFieldErrors] = useState<WebSourceFieldErrors>({});
  const foundCount = result.found_count ?? 0;
  // Zero jobs only comes back with an ATS hint; saving such a page would fail
  const hasNoVacancies = foundCount === 0;
  const titles = hasNoVacancies ? [] : (result.titles ?? []).slice(0, PREVIEW_TITLES_LIMIT);

  useEffect(() => {
    if (focusOnMount) headingRef.current?.focus();
  }, [focusOnMount]);

  /** Validated values, or null after showing field errors. */
  const validate = (): WebSourceOptions | null => {
    const parsed = webSourceOptionsSchema.safeParse({ jobLinkContains, name });
    if (parsed.success) {
      setFieldErrors({});
      return parsed.data;
    }
    setFieldErrors(toFieldErrors(parsed.error.issues));
    return null;
  };

  /** Validates and re-checks; resolves false when nothing was sent. */
  const runRecheck = async (): Promise<boolean> => {
    if (busy) return false;
    const values = validate();
    if (!values) return false;
    await onRecheck(values.jobLinkContains);
    return true;
  };

  const handleRecheckClick = async (): Promise<void> => {
    // The loading button was disabled (focus dropped); bring it back
    if (await runRecheck()) recheckButtonRef.current?.focus();
  };

  // Enter in the pattern field re-checks instead of saving; focus stays in the
  // field (it is only read-only while loading, so it keeps focus)
  const handlePatternKeyDown = (event: KeyboardEvent<HTMLInputElement>): void => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    void runRecheck();
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    if (busy || hasNoVacancies) return;
    const values = validate();
    if (!values) return;
    // On failure the loading Save button was disabled (focus dropped); bring it back
    if ((await onSave(values)) === false) saveButtonRef.current?.focus();
  };

  return (
    <section
      aria-labelledby={headingId}
      style={{
        border: `1px solid ${colors.border}`,
        borderRadius: "0.5rem",
        padding: "1rem",
        marginBottom: "1rem",
      }}
    >
      {/* Polite: a re-check's new count and titles are announced without stealing focus */}
      <div aria-live="polite">
        <h3
          id={headingId}
          ref={headingRef}
          tabIndex={-1}
          style={
            hasNoVacancies
              ? { fontSize: "0.875rem", fontWeight: 400, color: colors.textMuted }
              : { fontSize: "0.9375rem", fontWeight: 600, color: colors.textPrimary }
          }
        >
          {hasNoVacancies ? PREVIEW_NO_VACANCIES_TEXT : formatFoundCount(foundCount)}
        </h3>
        {titles.length > 0 ? (
          <ol
            style={{
              margin: "0.5rem 0 1rem",
              paddingLeft: "1.25rem",
              fontSize: "0.875rem",
              color: colors.textSecondary,
            }}
          >
            {titles.map((title, index) => (
              // Titles may repeat on a listing; position keeps keys unique
              <li key={`${index}-${title}`} style={{ overflowWrap: "anywhere" }}>
                {title}
              </li>
            ))}
          </ol>
        ) : null}
      </div>
      {result.ats_hint && onAddBoard ? (
        <AtsHint
          hint={result.ats_hint}
          busy={busy}
          isAdding={busyAction === "board"}
          onAddBoard={onAddBoard}
        />
      ) : null}
      <form onSubmit={(event) => void handleSubmit(event)} noValidate>
        <div style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem" }}>
          <div style={{ flex: 1 }}>
            <FormInput
              label={`${JOB_LINK_CONTAINS_LABEL} (optional)`}
              placeholder={JOB_LINK_CONTAINS_PLACEHOLDER}
              autoComplete="off"
              spellCheck={false}
              maxLength={JOB_LINK_CONTAINS_MAX_LENGTH}
              value={jobLinkContains}
              error={fieldErrors.jobLinkContains}
              readOnly={busy}
              onChange={(event) => setJobLinkContains(event.target.value)}
              onKeyDown={handlePatternKeyDown}
            />
          </div>
          <Button
            ref={recheckButtonRef}
            type="button"
            variant="secondary"
            loading={busyAction === "recheck"}
            disabled={busy && busyAction !== "recheck"}
            onClick={() => void handleRecheckClick()}
            style={{ marginTop: "1.5rem", flexShrink: 0 }}
          >
            Re-check
          </Button>
        </div>
        <FormInput
          label={`${SOURCE_NAME_LABEL} (optional)`}
          placeholder={result.default_name ?? undefined}
          autoComplete="off"
          maxLength={SOURCE_NAME_MAX_LENGTH}
          value={name}
          error={fieldErrors.name}
          readOnly={busy}
          onChange={(event) => setName(event.target.value)}
        />
        {error ? (
          <p role="alert" style={{ fontSize: "0.875rem", color: colors.error, marginBottom: "0.75rem" }}>
            {error}
          </p>
        ) : null}
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <Button
            ref={saveButtonRef}
            type="submit"
            loading={busyAction === "save"}
            disabled={hasNoVacancies || (busy && busyAction !== "save")}
          >
            Save
          </Button>
          <Button type="button" variant="secondary" disabled={busy} onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </form>
    </section>
  );
}
