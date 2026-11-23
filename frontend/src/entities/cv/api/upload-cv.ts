import { apiClient } from "@/shared/api";
import type { CvUploadResult } from "../model/types";

/** Create a new own CV from a PDF or DOCX file (`POST /cvs/upload`). */
export async function uploadCv(file: File): Promise<CvUploadResult> {
  const form = new FormData();
  form.append("file", file);
  return apiClient.postForm<CvUploadResult>("/api/v1/cvs/upload", form);
}
