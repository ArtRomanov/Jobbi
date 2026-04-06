import { apiClient } from "@/shared/api";
import type { Cv } from "../model/types";

export async function listCvs(): Promise<Cv[]> {
  return apiClient.get<Cv[]>("/api/v1/cvs");
}
