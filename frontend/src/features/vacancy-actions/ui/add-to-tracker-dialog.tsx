import { useEffect, useId, useMemo } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button, FormInput, FormSelect, FormTextarea, Modal, colors } from "@/shared/ui";
import type { Vacancy } from "@/entities/vacancy";
import {
  ADD_AND_TAILOR_LABEL,
  ADD_DIALOG_TITLE,
  ADD_TO_TRACKER_LABEL,
  BASE_CV_LABEL,
  CANCEL_LABEL,
  CVS_LOADING_HINT,
  CVS_LOAD_ERROR_HINT,
  MAX_NAME_LENGTH,
  NO_CVS_HINT,
} from "../lib/constants";
import { addToTrackerSchema, type AddToTrackerFormValues } from "../model/schemas";
import { useAddToTracker } from "../model/use-add-to-tracker";
import { useBaseCvs } from "../model/use-base-cvs";
import type { AddToTrackerCallbacks } from "../model/types";
import { DuplicateWarning } from "./duplicate-warning";

interface AddToTrackerDialogProps extends AddToTrackerCallbacks {
  vacancy: Vacancy;
}

/**
 * "Add to tracker" dialog for one Inbox card (functional spec 2.3). Render it
 * only while open. Company / role / notes are prefilled from the card; "Add &
 * tailor CV" also copies the chosen base CV (default: most recently updated).
 */
export function AddToTrackerDialog({ vacancy, onClose, onAdded, onMarkSeen }: AddToTrackerDialogProps) {
  const tailorHintId = useId();
  const duplicateTextId = useId();
  const { cvs, status: cvsStatus, defaultCvId } = useBaseCvs();
  const { isSubmitting, error, duplicate, duplicateAttention, submit, submitAnyway, openExisting } =
    useAddToTracker(vacancy, { onClose, onAdded, onMarkSeen });

  const {
    register,
    handleSubmit,
    setValue,
    getValues,
    formState: { errors },
  } = useForm<AddToTrackerFormValues>({
    resolver: zodResolver(addToTrackerSchema),
    defaultValues: {
      company_name: vacancy.company ?? "",
      role_title: vacancy.title ?? "",
      notes: vacancy.text,
      base_cv_id: "",
    },
  });

  // CVs arrive after the form mounts: preselect the default unless the user already picked one
  useEffect(() => {
    if (defaultCvId && getValues("base_cv_id") === "") setValue("base_cv_id", defaultCvId);
  }, [defaultCvId, getValues, setValue]);

  const cvOptions = useMemo(() => cvs.map((cv) => ({ value: cv.id, label: cv.name })), [cvs]);
  const hasCvs = cvs.length > 0;
  const tailorHint =
    cvsStatus === "loading"
      ? CVS_LOADING_HINT
      : cvsStatus === "error"
        ? CVS_LOAD_ERROR_HINT
        : hasCvs
          ? null
          : NO_CVS_HINT;

  return (
    <Modal
      title={ADD_DIALOG_TITLE}
      onClose={onClose}
      isDismissable={!isSubmitting}
      describedBy={duplicate ? duplicateTextId : undefined}
    >
      {duplicate ? (
        <DuplicateWarning
          application={duplicate}
          textId={duplicateTextId}
          attention={duplicateAttention}
          isDisabled={isSubmitting}
          onOpenExisting={openExisting}
          onAddAnyway={() => void handleSubmit((values) => submitAnyway(values))()}
        />
      ) : null}
      <form noValidate onSubmit={handleSubmit((values) => submit(values, "plain"))}>
        <FormInput
          label="Company"
          maxLength={MAX_NAME_LENGTH}
          error={errors.company_name?.message}
          {...register("company_name")}
        />
        <FormInput
          label="Role"
          maxLength={MAX_NAME_LENGTH}
          error={errors.role_title?.message}
          {...register("role_title")}
        />
        <FormTextarea label="Notes" rows={6} {...register("notes")} />
        {hasCvs ? <FormSelect label={BASE_CV_LABEL} options={cvOptions} {...register("base_cv_id")} /> : null}

        {error ? (
          <p role="alert" style={{ margin: "0 0 1rem", fontSize: "0.875rem", color: colors.error }}>
            {error}
          </p>
        ) : null}

        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", justifyContent: "flex-end" }}>
          <Button type="button" variant="secondary" disabled={isSubmitting} onClick={onClose}>
            {CANCEL_LABEL}
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={!hasCvs || isSubmitting}
            aria-describedby={tailorHint ? tailorHintId : undefined}
            onClick={() => void handleSubmit((values) => submit(values, "tailor"))()}
          >
            {ADD_AND_TAILOR_LABEL}
          </Button>
          <Button type="submit" loading={isSubmitting}>
            {ADD_TO_TRACKER_LABEL}
          </Button>
        </div>
        {tailorHint ? (
          <p
            id={tailorHintId}
            style={{ margin: "0.5rem 0 0", fontSize: "0.75rem", color: colors.textMuted, textAlign: "right" }}
          >
            {tailorHint}
          </p>
        ) : null}
      </form>
    </Modal>
  );
}
