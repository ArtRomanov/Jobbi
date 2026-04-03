import type { components } from "@/shared/api";

/** Core user profile returned by GET /api/v1/users/me */
export type User = components["schemas"]["UserRead"];

/** Fields that can be updated via PATCH /api/v1/users/me */
export type UserUpdate = components["schemas"]["UserUpdate"];