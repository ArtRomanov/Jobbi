import { useRef, useState, type ChangeEvent } from "react";
import { useNavigate } from "react-router-dom";
import { uploadCv } from "@/entities/cv";
import { Button, useToast } from "@/shared/ui";
import {
  getUploadErrorMessage,
  MAX_UPLOAD_BYTES,
  UPLOAD_ERROR_MESSAGES,
} from "../lib/upload-error-message";
import type { UploadNoticeRouterState } from "../model/upload-notice-state";

/**
 * "Upload CV": picks one PDF/DOCX, uploads it, then opens the new CV's editor
 * with the upload notice in router state (read by `UploadNotice`).
 */
export function UploadCvButton() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);
  const navigate = useNavigate();
  const { showToast } = useToast();

  async function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    // Clear it so picking the same file again fires `change` again.
    input.value = "";
    if (!file || isUploading) return;

    // Same limit as the server: skip sending a file it would refuse.
    if (file.size > MAX_UPLOAD_BYTES) {
      showToast(UPLOAD_ERROR_MESSAGES.FILE_TOO_LARGE, "error");
      return;
    }

    setIsUploading(true);
    try {
      const cv = await uploadCv(file);
      const state: UploadNoticeRouterState = {
        uploadNotice: { truncated: cv.truncated, becameBase: cv.became_base },
      };
      void navigate(`/cvs/${cv.id}/edit`, { state });
    } catch (error: unknown) {
      showToast(getUploadErrorMessage(error), "error");
      setIsUploading(false);
    }
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx"
        hidden
        data-testid="cv-upload-input"
        onChange={(event) => void handleChange(event)}
      />
      <Button
        type="button"
        variant="secondary"
        disabled={isUploading}
        aria-busy={isUploading || undefined}
        onClick={() => inputRef.current?.click()}
      >
        {isUploading ? "Uploading…" : "Upload CV"}
      </Button>
    </>
  );
}
