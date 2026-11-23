import { apiClient } from "@/shared/api";
import type { Cv } from "../model/types";

/**
 * Make this CV the user's base CV (`POST /cvs/{id}/make-base`). The previous
 * base becomes an ordinary own CV; a tailored copy comes back as `kind: "own"`.
 */
export async function makeBaseCv(id: string): Promise<Cv> {
  return apiClient.post<Cv>(`/api/v1/cvs/${encodeURIComponent(id)}/make-base`, undefined);
}
