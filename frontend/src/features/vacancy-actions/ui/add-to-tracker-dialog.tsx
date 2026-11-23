import { useEffect, useId, useMemo } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button, FormInput, FormSelect, FormTextarea, Modal, colors } from "@/shared/ui";
import type { Vacancy } from "@/entities/vacancy";
import { buildCvSelectChoices } from "@/entities/cv";
import {
  ADD_AND_TAILOR_LABEL,
  ADD_DIALOG_TITLE,
  ADD_TO_TRACKER_LABEL,
  CANCEL_LABEL,
  CHOOSE_CV_PLACEHOLDER,
  CV_SELECT_LABEL,
  CVS_LOADING_HINT,
  CVS_LOAD_ERROR_HINT,
  MAX_NAME_LENGTH,
  NO_BASE_CV_HINT,
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
 * tailor CV" also copies the chosen CV. The base CV is preselected; with no
 * base nothing is, and "Add & tailor CV" waits for a choice (spec 011 §2.6).
 */
export function AddToTrackerDialog({ vacancy, onClose, onAdded, onMarkSeen }: AddToTrackerDialogProps) {
  const tailorHintId = useId();
  const cvHintId = useId();
  const duplicateTextId = useId();
  const { cvs, status: cvsStatus, defaultCvId } = useBaseCvs();
  const { isSubmitting, error, duplicate, duplicateAttention, submit, submitAnyway, openExisting } =
    useAddToTracker(vacancy, { onClose, onAdded, onMarkSeen });

  const {
    register,
    handleSubmit,
    setValue,
    getValues,
    control,
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

  const selectedCvId = useWatch({ control, name: "base_cv_id" });
  const hasCvs = cvs.length > 0;
  const hasBase = defaultCvId !== null;
  // Own CVs (base first, "(base)"), then the "Tailored copies" group. With no
  // base an empty first choice keeps the select on "nothing chosen".
  const cvChoices = useMemo(() => {
    const { options, groups } = buildCvSelectChoices(cvs);
    return {
      options: hasBase ? options : [{ value: "", label: CHOOSE_CV_PLACEHOLDER }, ...options],
      groups,
    };
  }, [cvs, hasBase]);
  const showNoBaseHint = hasCvs && !hasBase;
  const isCvChosen = selectedCvId !== "";
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
        {hasCvs ? (
          <FormSelect
            label={CV_SELECT_LABEL}
            options={cvChoices.options}
            groups={cvChoices.groups}
            aria-describedby={showNoBaseHint ? cvHintId : undefined}
            {...register("base_cv_id")}
          />
        ) : null}
        {showNoBaseHint ? (
          <p
            id={cvHintId}
            style={{ margin: "-0.5rem 0 1rem", fontSize: "0.75rem", color: colors.textMuted }}
          >
            {NO_BASE_CV_HINT}
          </p>
        ) : null}

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
            disabled={!hasCvs || !isCvChosen || isSubmitting}
            aria-describedby={
              tailorHint ? tailorHintId : showNoBaseHint && !isCvChosen ? cvHintId : undefined
            }
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
