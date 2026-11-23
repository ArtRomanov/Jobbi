import { apiClient } from "@/shared/api";
import type { CvUploadResult } from "../model/types";

/**
 * Extract the text of a PDF or DOCX file (`POST /cvs/upload`). Creates
 * nothing: the result opens as an unsaved draft in the editor.
 */
export async function uploadCv(file: File): Promise<CvUploadResult> {
  const form = new FormData();
  form.append("file", file);
  return apiClient.postForm<CvUploadResult>("/api/v1/cvs/upload", form);
}
