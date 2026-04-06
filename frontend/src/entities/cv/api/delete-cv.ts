import { apiClient } from "@/shared/api";

export async function deleteCv(id: string): Promise<{ message: string }> {
  return apiClient.delete<{ message: string }>(`/api/v1/cvs/${id}`);
}
