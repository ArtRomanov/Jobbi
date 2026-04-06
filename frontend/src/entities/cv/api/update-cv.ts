import { apiClient } from "@/shared/api";
import type { Cv, CvUpdate } from "../model/types";

export async function updateCv(id: string, data: CvUpdate): Promise<Cv> {
  return apiClient.patch<Cv>(`/api/v1/cvs/${id}`, data);
}
