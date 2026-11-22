import { isApiError } from "@/shared/api";
import type { ExistingApplicationRef } from "../model/types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/**
 * The tracked application from add-to-tracker's structured 409
 * (`{"detail": {"message", "application": {id, company_name, role_title}}}`),
 * or null for any other error. Other 409s carry a string `detail`.
 */
export function getDuplicateApplication(error: unknown): ExistingApplicationRef | null {
  if (!isApiError(error) || error.status !== 409 || !isRecord(error.body)) return null;
  const { detail } = error.body;
  if (!isRecord(detail) || !isRecord(detail.application)) return null;
  const { id, company_name, role_title } = detail.application;
  if (typeof id !== "string" || typeof company_name !== "string" || typeof role_title !== "string") {
    return null;
  }
  return { id, company_name, role_title };
}
