import { colors } from "@/shared/ui";

export const UPLOAD_NOTICE_TEXT =
  "Text extracted from your file. Review it and save to add it to your CVs.";
export const UPLOAD_CUT_TEXT =
  "The text was longer than 20 000 characters and was cut.";

interface UploadNoticeProps {
  /** The extracted text was cut to 20 000 characters. */
  truncated: boolean;
}

/** Notice above the editor while an uploaded draft is not saved yet. */
export function UploadNotice({ truncated }: UploadNoticeProps) {
  return (
    <div
      role="status"
      style={{
        padding: "0.75rem 1rem",
        marginBottom: "1rem",
        borderRadius: "0.375rem",
        border: `1px solid ${colors.border}`,
        backgroundColor: colors.bgCard,
        color: colors.textPrimary,
        fontSize: "0.875rem",
      }}
    >
      <p style={{ margin: 0 }}>{UPLOAD_NOTICE_TEXT}</p>
      {truncated ? <p style={{ margin: "0.25rem 0 0" }}>{UPLOAD_CUT_TEXT}</p> : null}
    </div>
  );
}
