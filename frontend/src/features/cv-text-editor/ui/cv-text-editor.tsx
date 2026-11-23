import { useState, type FormEvent } from "react";
import { Button, FormInput, SegmentedControl, colors } from "@/shared/ui";
import type { SegmentedControlOption } from "@/shared/ui";
import { CV_NAME_MAX_LENGTH, PHONE_MEDIA_QUERY } from "../config";
import { useMediaQuery } from "../lib/use-media-query";
import type { CvTextEditorValues } from "../model/types";
import { useCvTextDraft } from "../model/use-cv-text-draft";
import { CvContentField } from "./cv-content-field";
import { CvPreviewPane } from "./cv-preview-pane";

type EditorTab = "edit" | "preview";

const TAB_OPTIONS: readonly SegmentedControlOption<EditorTab>[] = [
  { value: "edit", label: "Edit" },
  { value: "preview", label: "Preview" },
];

const PANE_LABEL_STYLE = {
  display: "block",
  marginBottom: "0.25rem",
  fontSize: "0.875rem",
  fontWeight: 500,
  color: colors.textSecondary,
} as const;

interface CvTextEditorProps {
  /** Values the editor starts from; read once on mount. */
  initialValues: CvTextEditorValues;
  /** Called with the trimmed name and the text. Errors are the caller's to show. */
  onSave: (values: CvTextEditorValues) => Promise<void>;
  isSaving: boolean;
}

/**
 * Name + one free-text CV with a live preview: side by side on wide screens,
 * "Edit" / "Preview" tabs on phone width. A `feature/` because it is the
 * user's "edit my CV" interaction; saving itself is wired by the page.
 */
export function CvTextEditor({ initialValues, onSave, isSaving }: CvTextEditorProps) {
  const draft = useCvTextDraft(initialValues);
  const isPhone = useMediaQuery(PHONE_MEDIA_QUERY);
  const [tab, setTab] = useState<EditorTab>("edit");

  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (isSaving) return;
    const values = draft.validate();
    if (!values) return;
    // Show the name as it is saved (trimmed)
    if (values.name !== draft.name) draft.setName(values.name);
    void onSave(values);
  }

  const contentField = <CvContentField value={draft.content} onChange={draft.setContent} />;

  return (
    <form onSubmit={handleSubmit} noValidate>
      <FormInput
        label="CV Name"
        value={draft.name}
        maxLength={CV_NAME_MAX_LENGTH}
        required
        error={draft.nameError ?? undefined}
        onChange={(event) => draft.setName(event.target.value)}
      />

      {isPhone ? (
        <>
          <div style={{ marginBottom: "0.75rem" }}>
            <SegmentedControl label="Editor view" options={TAB_OPTIONS} value={tab} onChange={setTab} />
          </div>
          {tab === "edit" ? contentField : <CvPreviewPane content={draft.content} />}
        </>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)",
            gap: "1.5rem",
            alignItems: "start",
          }}
        >
          {contentField}
          <div>
            <span style={PANE_LABEL_STYLE} aria-hidden="true">
              Preview
            </span>
            <CvPreviewPane content={draft.content} />
          </div>
        </div>
      )}

      <div style={{ marginTop: "1rem" }}>
        <Button type="submit" loading={isSaving}>
          Save
        </Button>
      </div>
    </form>
  );
}
