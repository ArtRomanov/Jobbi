import { useCallback } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { VacancySource } from "@/entities/vacancy-source";
import { Button, FormInput, Modal, colors } from "@/shared/ui";
import {
  CANCEL_LABEL,
  EDIT_SOURCE_TITLE,
  JOB_LINK_CONTAINS_LABEL,
  JOB_LINK_CONTAINS_PLACEHOLDER,
  SAVE_LABEL,
  SOURCE_LINK_LABEL,
  SOURCE_NAME_HINT,
  SOURCE_NAME_LABEL,
} from "../lib/constants";
import { getSourceLink } from "../lib/helpers";
import { editSourceSchema, type EditSourceFormInput, type EditSourceValues } from "../model/schemas";
import type { SourceEditedHandler } from "../model/types";
import { useEditSource } from "../model/use-edit-source";
import { SourcePreview } from "./source-preview";

interface EditSourceDialogProps {
  source: VacancySource;
  onClose: () => void;
  /** Gets the server's copy (a replaced source has a new id); the caller closes the dialog. */
  onSaved: SourceEditedHandler;
}

/**
 * "Edit source" dialog (render only while open): name, link and, for a web
 * page, "Job link contains". A changed link / pattern that is a web page shows
 * `SourcePreview` (found N, titles, re-check) in place of the form before the
 * final Save; Cancel there goes back to the form. Escape / backdrop are
 * blocked while a request runs; errors show inline.
 */
export function EditSourceDialog({ source, onClose, onSaved }: EditSourceDialogProps) {
  const { busyAction, isBusy, error, preview, previewError, submit, recheck, savePreview, closePreview } =
    useEditSource(source, onSaved);
  const isWeb = source.kind === "web";
  const {
    register,
    handleSubmit,
    setFocus,
    formState: { errors },
  } = useForm<EditSourceFormInput, unknown, EditSourceValues>({
    resolver: zodResolver(editSourceSchema),
    defaultValues: {
      // A default-named source starts empty so saving keeps it following the default
      name: source.name_is_custom ? source.display_name : "",
      link: getSourceLink(source),
      jobLinkContains: source.job_link_contains ?? "",
    },
  });

  // A failed save leaves the user on the field they changed, next to the error
  const handleValidSubmit = useCallback(
    async (values: EditSourceValues): Promise<void> => {
      const fieldToFocus = await submit(values);
      if (fieldToFocus !== null) setFocus(fieldToFocus);
    },
    [submit, setFocus],
  );

  const handleBack = useCallback((): void => {
    closePreview();
    // The form is only hidden, so its drafts are kept; wait for it to show again
    requestAnimationFrame(() => setFocus("link"));
  }, [closePreview, setFocus]);

  return (
    <Modal title={EDIT_SOURCE_TITLE} onClose={onClose} isDismissable={!isBusy}>
      {preview ? (
        <>
          <p style={{ margin: "0 0 0.75rem", fontSize: "0.875rem", color: colors.textSecondary, overflowWrap: "anywhere" }}>
            {`${SOURCE_LINK_LABEL}: ${preview.input}`}
          </p>
          <SourcePreview
            key={preview.id}
            result={preview.result}
            initialJobLinkContains={preview.initialJobLinkContains}
            initialName={preview.initialName}
            busy={isBusy}
            busyAction={busyAction === "check" ? null : busyAction}
            error={previewError}
            onRecheck={recheck}
            onSave={savePreview}
            onCancel={handleBack}
          />
        </>
      ) : null}
      {/* Hidden (not unmounted) under a preview so the drafts survive going back */}
      <form noValidate hidden={preview !== null} onSubmit={(event) => void handleSubmit(handleValidSubmit)(event)}>
        <FormInput
          label={SOURCE_NAME_LABEL}
          // Not custom → display_name is the default name; else it is unknown here
          placeholder={source.display_name}
          autoComplete="off"
          hint={SOURCE_NAME_HINT}
          error={errors.name?.message}
          readOnly={isBusy}
          {...register("name")}
        />
        <FormInput
          label={SOURCE_LINK_LABEL}
          autoComplete="off"
          spellCheck={false}
          error={errors.link?.message}
          readOnly={isBusy}
          {...register("link")}
        />
        {isWeb ? (
          <FormInput
            label={`${JOB_LINK_CONTAINS_LABEL} (optional)`}
            placeholder={JOB_LINK_CONTAINS_PLACEHOLDER}
            autoComplete="off"
            spellCheck={false}
            error={errors.jobLinkContains?.message}
            readOnly={isBusy}
            {...register("jobLinkContains")}
          />
        ) : null}
        {error ? (
          <p role="alert" style={{ margin: "0 0 1rem", fontSize: "0.875rem", color: colors.error }}>
            {error}
          </p>
        ) : null}
        <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
          <Button type="button" variant="secondary" disabled={isBusy} onClick={onClose}>
            {CANCEL_LABEL}
          </Button>
          <Button type="submit" loading={busyAction === "check"}>
            {SAVE_LABEL}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
