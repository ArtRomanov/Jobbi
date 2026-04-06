import { apiClient } from "@/shared/api";
import type { Cv, CvCreate } from "../model/types";

export async function createCv(data: CvCreate): Promise<Cv> {
  return apiClient.post<Cv>("/api/v1/cvs", data);
}
