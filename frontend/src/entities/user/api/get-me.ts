import { apiClient } from "@/shared/api";
import type { User } from "../model/types";

/** Fetch the authenticated user's profile. */
export async function getMe(): Promise<User> {
  return apiClient.get<User>("/api/v1/users/me");
}
