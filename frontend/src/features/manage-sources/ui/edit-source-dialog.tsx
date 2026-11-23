import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { VacancySource } from "@/entities/vacancy-source";
import { Button, FormInput, Modal, colors } from "@/shared/ui";
import {
  CANCEL_LABEL,
  EDIT_SOURCE_TITLE,
  SAVE_LABEL,
  SOURCE_NAME_HINT,
  SOURCE_NAME_LABEL,
} from "../lib/constants";
import { editSourceSchema, type EditSourceFormInput, type EditSourceValues } from "../model/schemas";
import type { SourceEditedHandler } from "../model/types";
import { useEditSource } from "../model/use-edit-source";

interface EditSourceDialogProps {
  source: VacancySource;
  onClose: () => void;
  /** Gets the server's copy; the caller closes the dialog. */
  onSaved: SourceEditedHandler;
}

/**
 * "Edit source" dialog (render only while open). Name only for now; Slice 6
 * adds the link + "Job link contains" fields and a `SourcePreview` before Save.
 * Escape / backdrop are blocked while saving; errors show inline.
 */
export function EditSourceDialog({ source, onClose, onSaved }: EditSourceDialogProps) {
  const { isSaving, error, save } = useEditSource(source.id, onSaved);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<EditSourceFormInput, unknown, EditSourceValues>({
    resolver: zodResolver(editSourceSchema),
    // A default-named source starts empty so saving keeps it following the default
    defaultValues: { name: source.name_is_custom ? source.display_name : "" },
  });

  return (
    <Modal title={EDIT_SOURCE_TITLE} onClose={onClose} isDismissable={!isSaving}>
      <form noValidate onSubmit={(event) => void handleSubmit(save)(event)}>
        <FormInput
          label={SOURCE_NAME_LABEL}
          // Not custom → display_name is the default name; else it is unknown here
          placeholder={source.display_name}
          autoComplete="off"
          hint={SOURCE_NAME_HINT}
          error={errors.name?.message}
          readOnly={isSaving}
          {...register("name")}
        />
        {error ? (
          <p role="alert" style={{ margin: "0 0 1rem", fontSize: "0.875rem", color: colors.error }}>
            {error}
          </p>
        ) : null}
        <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
          <Button type="button" variant="secondary" disabled={isSaving} onClick={onClose}>
            {CANCEL_LABEL}
          </Button>
          <Button type="submit" loading={isSaving}>
            {SAVE_LABEL}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
