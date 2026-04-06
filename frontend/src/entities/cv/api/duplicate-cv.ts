import { apiClient } from "@/shared/api";
import type { Cv, CvDuplicateRequest } from "../model/types";

export async function duplicateCv(
  id: string,
  name?: string,
): Promise<Cv> {
  const body: CvDuplicateRequest = { name: name ?? null };
  return apiClient.post<Cv>(`/api/v1/cvs/${id}/duplicate`, body);
}
