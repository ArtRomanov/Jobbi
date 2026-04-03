import { useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import {
  getApplication,
  updateApplication,
  deleteApplication,
  STATUSES,
  type ApplicationDetail,
  type ApplicationUpdate,
  type StatusHistory,
} from "@/entities/application";
import { Button, FormInput, FormSelect, FormTextarea, colors, useToast } from "@/shared/ui";
import { handleApiError } from "@/shared/api";

/**
 * Form values mirror the editable fields of an application.
 * Numeric fields use string representation for form inputs;
 * we convert back to numbers before sending to the API.
 */
interface FormValues {
  company_name: string;
  role_title: string;
  job_url: string;
  salary_min: string;
  salary_max: string;
  salary_currency: string;
  contact_name: string;
  contact_email: string;
  notes: string;
  status: string;
}

interface ApplicationPanelProps {
  applicationId: string | null;
  onClose: () => void;
  onUpdate: () => void;
}

const STATUS_OPTIONS = STATUSES.map((s) => ({ value: s.key, label: s.label }));

function toFormValues(detail: ApplicationDetail): FormValues {
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

function buildDirtyPayload(
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

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function statusLabel(key: string): string {
  const found = STATUSES.find((s) => s.key === key);
  return found ? found.label : key;
}

/**
 * Side panel drawer showing full application details with inline editing.
 * This is a `feature/` because it encapsulates a user interaction (viewing
 * and editing application details), not just a domain entity display.
 */
export function ApplicationPanel({
  applicationId,
  onClose,
  onUpdate,
}: ApplicationPanelProps) {
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const { showToast } = useToast();

  const {
    register,
    handleSubmit,
    reset,
    formState: { dirtyFields, isDirty },
  } = useForm<FormValues>();

  // Fetch application detail when applicationId changes
  useEffect(() => {
    if (!applicationId) {
      setDetail(null);
      setError(null);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setError(null);
    setShowDeleteConfirm(false);

    getApplication(applicationId)
      .then((data) => {
        if (!cancelled) {
          setDetail(data);
          reset(toFormValues(data));
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load application",
          );
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [applicationId, reset]);

  // Close on Escape key
  useEffect(() => {
    if (!applicationId) return;

    function handleKeyDown(e: KeyboardEvent): void {
      if (e.key === "Escape") {
        onClose();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [applicationId, onClose]);

  const onSave = useCallback(
    async (values: FormValues): Promise<void> => {
      if (!applicationId || !isDirty) return;

      const payload = buildDirtyPayload(dirtyFields, values);
      if (Object.keys(payload).length === 0) return;

      setIsSaving(true);
      try {
        const updated = await updateApplication(applicationId, payload);
        setDetail(updated);
        reset(toFormValues(updated));
        showToast("Application updated.", "success");
        onUpdate();
      } catch (err: unknown) {
        handleApiError(err, showToast);
      } finally {
        setIsSaving(false);
      }
    },
    [applicationId, isDirty, dirtyFields, reset, showToast, onUpdate],
  );

  const onDelete = useCallback(async (): Promise<void> => {
    if (!applicationId) return;

    setIsDeleting(true);
    try {
      await deleteApplication(applicationId);
      showToast("Application deleted.", "success");
      onUpdate();
      onClose();
    } catch (err: unknown) {
      handleApiError(err, showToast);
    } finally {
      setIsDeleting(false);
    }
  }, [applicationId, showToast, onUpdate, onClose]);

  const handleOverlayClick = useCallback(() => {
    onClose();
  }, [onClose]);

  const isOpen = applicationId !== null;

  if (!isOpen) return null;

  return (
    <>
      {/* Overlay / backdrop */}
      <div
        onClick={handleOverlayClick}
        aria-hidden="true"
        style={{
          position: "fixed",
          inset: 0,
          backgroundColor: "rgba(0, 0, 0, 0.3)",
          zIndex: 1000,
        }}
      />

      {/* Panel */}
      <aside
        role="dialog"
        aria-label="Application details"
        style={{
          position: "fixed",
          top: 0,
          right: 0,
          bottom: 0,
          width: 480,
          maxWidth: "100vw",
          backgroundColor: colors.bgCard,
          boxShadow: "-4px 0 24px rgba(0, 0, 0, 0.12)",
          zIndex: 1001,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "1rem 1.25rem",
            borderBottom: `1px solid ${colors.borderLight}`,
            flexShrink: 0,
          }}
        >
          <h2
            style={{
              margin: 0,
              fontSize: "1.125rem",
              fontWeight: 600,
              color: colors.textPrimary,
            }}
          >
            Application Details
          </h2>
          <button
            onClick={onClose}
            aria-label="Close panel"
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              padding: "0.25rem",
              fontSize: "1.25rem",
              color: colors.textMuted,
              lineHeight: 1,
            }}
          >
            &#x2715;
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: "auto", padding: "1.25rem" }}>
          {isLoading && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                minHeight: "20vh",
                color: colors.textMuted,
                fontSize: "0.875rem",
              }}
            >
              Loading...
            </div>
          )}

          {error && (
            <div
              style={{
                color: colors.error,
                fontSize: "0.875rem",
                padding: "1rem 0",
              }}
            >
              {error}
            </div>
          )}

          {!isLoading && !error && detail && (
            <form onSubmit={handleSubmit(onSave)}>
              <FormInput
                label="Company Name"
                {...register("company_name", {
                  required: "Company name is required",
                })}
              />

              <FormInput
                label="Role Title"
                {...register("role_title", {
                  required: "Role title is required",
                })}
              />

              <FormInput
                label="Job URL"
                type="url"
                {...register("job_url")}
              />

              {/* Display job URL as clickable link when set */}
              {detail.job_url && (
                <div style={{ marginTop: "-0.5rem", marginBottom: "1rem" }}>
                  <a
                    href={detail.job_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      fontSize: "0.75rem",
                      color: colors.primary,
                      textDecoration: "underline",
                    }}
                  >
                    Open job posting
                  </a>
                </div>
              )}

              <div style={{ display: "flex", gap: "0.75rem" }}>
                <div style={{ flex: 1 }}>
                  <FormInput
                    label="Salary Min"
                    type="number"
                    {...register("salary_min")}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <FormInput
                    label="Salary Max"
                    type="number"
                    {...register("salary_max")}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <FormInput
                    label="Currency"
                    placeholder="USD"
                    {...register("salary_currency")}
                  />
                </div>
              </div>

              <FormInput
                label="Contact Name"
                {...register("contact_name")}
              />

              <FormInput
                label="Contact Email"
                type="email"
                {...register("contact_email")}
              />

              <FormSelect
                label="Status"
                options={STATUS_OPTIONS}
                {...register("status")}
              />

              <FormTextarea
                label="Notes"
                rows={4}
                {...register("notes")}
              />

              {/* Created date (read-only) */}
              <div style={{ marginBottom: "1.5rem" }}>
                <span
                  style={{
                    fontSize: "0.75rem",
                    color: colors.textMuted,
                  }}
                >
                  Created: {formatDate(detail.created_at)}
                </span>
              </div>

              {/* Action buttons */}
              <div
                style={{
                  display: "flex",
                  gap: "0.75rem",
                  marginBottom: "2rem",
                }}
              >
                <Button type="submit" loading={isSaving} disabled={!isDirty}>
                  Save Changes
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  style={{
                    color: colors.error,
                    borderColor: colors.error,
                  }}
                  onClick={() => setShowDeleteConfirm(true)}
                >
                  Delete
                </Button>
              </div>

              {/* Delete confirmation */}
              {showDeleteConfirm && (
                <div
                  style={{
                    padding: "1rem",
                    backgroundColor: colors.bgPage,
                    borderRadius: "0.375rem",
                    border: `1px solid ${colors.border}`,
                    marginBottom: "2rem",
                  }}
                >
                  <p
                    style={{
                      margin: "0 0 0.75rem",
                      fontSize: "0.875rem",
                      color: colors.textPrimary,
                    }}
                  >
                    Are you sure you want to delete this application? This
                    action cannot be undone.
                  </p>
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <Button
                      type="button"
                      loading={isDeleting}
                      style={{
                        backgroundColor: colors.error,
                      }}
                      onClick={onDelete}
                    >
                      Confirm Delete
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => setShowDeleteConfirm(false)}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              )}

              {/* Status history */}
              {detail.status_history.length > 0 && (
                <div>
                  <h3
                    style={{
                      fontSize: "0.875rem",
                      fontWeight: 600,
                      color: colors.textPrimary,
                      marginBottom: "0.5rem",
                    }}
                  >
                    Status History
                  </h3>
                  <ul
                    style={{
                      listStyle: "none",
                      margin: 0,
                      padding: 0,
                    }}
                  >
                    {[...detail.status_history]
                      .sort(
                        (a: StatusHistory, b: StatusHistory) =>
                          new Date(a.changed_at).getTime() -
                          new Date(b.changed_at).getTime(),
                      )
                      .map((entry: StatusHistory) => (
                        <li
                          key={entry.id}
                          style={{
                            fontSize: "0.8125rem",
                            color: colors.textSecondary,
                            padding: "0.375rem 0",
                            borderBottom: `1px solid ${colors.borderLight}`,
                          }}
                        >
                          Changed to{" "}
                          <strong>{statusLabel(entry.status)}</strong>
                          {" \u2014 "}
                          {formatDate(entry.changed_at)}
                        </li>
                      ))}
                  </ul>
                </div>
              )}
            </form>
          )}
        </div>
      </aside>
    </>
  );
}
