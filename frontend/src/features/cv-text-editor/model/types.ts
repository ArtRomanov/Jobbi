/** What the editor hands to `onSave`: the name is already trimmed and non-empty. */
export interface CvTextEditorValues {
  name: string;
  content: string;
  /** The "Base CV" switch. */
  isBase: boolean;
}

/** What "Export PDF" gets: the current name (trimmed) and text. */
export type CvTextExportValues = Pick<CvTextEditorValues, "name" | "content">;
