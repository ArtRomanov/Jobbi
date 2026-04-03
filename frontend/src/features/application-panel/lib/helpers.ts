import { STATUSES, type ApplicationDetail, type ApplicationUpdate } from "@/entities/application";
import type { FormValues } from "../model/types";

export function toFormValues(detail: ApplicationDetail): FormValues {
  return {
    company_name: detail.company_name,
    role_title: detail.role_title,
    job_url: detail.job_url ?? "",
    salary_min: detail.salary_min != null ? String(detail.salary_min) : "",
    salary_max: detail.salary_max != null ? String(detail.salary_max) : "",
    salary_currency: detail.salary_currency ?? "",
    contact_name: detail.contact_name ?? "",
    contact_email: detail.contact_email ?? "",
    notes: detail.notes ?? "",
    status: detail.status,
  };
}

export function buildDirtyPayload(
  dirtyFields: Partial<Record<keyof FormValues, boolean>>,
  values: FormValues,
): ApplicationUpdate {
  const payload: ApplicationUpdate = {};

  if (dirtyFields.company_name) payload.company_name = values.company_name;
  if (dirtyFields.role_title) payload.role_title = values.role_title;
  if (dirtyFields.job_url)
    payload.job_url = values.job_url || null;
  if (dirtyFields.salary_min)
    payload.salary_min = values.salary_min ? Number(values.salary_min) : null;
  if (dirtyFields.salary_max)
    payload.salary_max = values.salary_max ? Number(values.salary_max) : null;
  if (dirtyFields.salary_currency)
    payload.salary_currency = values.salary_currency || null;
  if (dirtyFields.contact_name)
    payload.contact_name = values.contact_name || null;
  if (dirtyFields.contact_email)
    payload.contact_email = values.contact_email || null;
  if (dirtyFields.notes) payload.notes = values.notes || null;
  if (dirtyFields.status) payload.status = values.status;

  return payload;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function statusLabel(key: string): string {
  const found = STATUSES.find((s) => s.key === key);
  return found ? found.label : key;
}
