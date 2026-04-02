/** Core user profile returned by GET /api/v1/users/me */
export interface User {
  id: string;
  email: string;
  full_name: string;
  desired_role: string | null;
  desired_location: string | null;
  remote_preference: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  created_at: string;
}

/** Fields that can be updated via PATCH /api/v1/users/me */
export interface UserUpdate {
  full_name?: string;
  desired_role?: string | null;
  desired_location?: string | null;
  remote_preference?: string | null;
  salary_min?: number | null;
  salary_max?: number | null;
  salary_currency?: string | null;
}
