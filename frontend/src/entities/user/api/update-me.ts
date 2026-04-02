import { apiClient } from "@/shared/api";
import type { User, UserUpdate } from "../model/types";

/** Patch the authenticated user's profile with changed fields only. */
export async function updateMe(data: UserUpdate): Promise<User> {
  return apiClient.patch<User>("/api/v1/users/me", data);
}
