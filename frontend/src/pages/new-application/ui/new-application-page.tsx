import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate } from "react-router-dom";
import { isApiError } from "@/shared/api";
import { FormInput, Button, useToast, colors } from "@/shared/ui";
import { createApplication } from "@/entities/application";

const APPLICATION_STATUSES = [
  { value: "researching", label: "Researching" },
  { value: "applied", label: "Applied" },
  { value: "interview", label: "Interview" },
  { value: "offer", label: "Offer" },
  { value: "rejected", label: "Rejected" },
  { value: "withdrawn", label: "Withdrawn" },
] as const;

const newApplicationSchema = z.object({
  company_name: z.string().min(1, "Company name is required"),
  role_title: z.string().min(1, "Role title is required"),
  job_url: z.string().optional(),
  salary_min: z.string().optional(),
  salary_max: z.string().optional(),
  salary_currency: z.string().optional(),
  contact_name: z.string().optional(),
  contact_email: z.string().optional(),
  notes: z.string().optional(),
  status: z.enum(["researching", "applied", "interview", "offer", "rejected", "withdrawn"]),
});

type NewApplicationFormData = z.infer<typeof newApplicationSchema>;

export function NewApplicationPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<NewApplicationFormData>({
    resolver: zodResolver(newApplicationSchema),
    defaultValues: {
      status: "researching",
    },
  });

  const onSubmit = async (data: NewApplicationFormData) => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      const body = {
        company_name: data.company_name,
        role_title: data.role_title,
        status: data.status,
        ...(data.job_url ? { job_url: data.job_url } : {}),
        ...(data.salary_min ? { salary_min: Number(data.salary_min) } : {}),
        ...(data.salary_max ? { salary_max: Number(data.salary_max) } : {}),
        ...(data.salary_currency ? { salary_currency: data.salary_currency } : {}),
        ...(data.contact_name ? { contact_name: data.contact_name } : {}),
        ...(data.contact_email ? { contact_email: data.contact_email } : {}),
        ...(data.notes ? { notes: data.notes } : {}),
      };

      await createApplication(body);
      showToast("Application created!", "success");
      navigate("/dashboard");
    } catch (error: unknown) {
      if (isApiError(error)) {
        showToast("Failed to create application. Please try again.", "error");
      } else {
        showToast("Network error. Check your connection.", "error");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      style={{
        maxWidth: "560px",
        margin: "2rem auto",
        padding: "2rem",
        backgroundColor: colors.bgCard,
        borderRadius: "0.5rem",
        boxShadow: "0 1px 3px rgba(0, 0, 0, 0.1)",
      }}
    >
      <h1
        style={{
          fontSize: "1.5rem",
          fontWeight: 700,
          marginBottom: "0.25rem",
          color: colors.textPrimary,
        }}
      >
        New Application
      </h1>
      <p
        style={{
          fontSize: "0.875rem",
          color: colors.textMuted,
          marginBottom: "1.5rem",
        }}
      >
        Track a new job opportunity
      </p>

      <form onSubmit={handleSubmit(onSubmit)}>
        <FormInput
          label="Company Name *"
          type="text"
          placeholder="e.g. Acme Corp"
          error={errors.company_name?.message}
          {...register("company_name")}
        />
        <FormInput
          label="Role Title *"
          type="text"
          placeholder="e.g. Senior Frontend Engineer"
          error={errors.role_title?.message}
          {...register("role_title")}
        />
        <FormInput
          label="Job Posting URL"
          type="url"
          placeholder="https://..."
          error={errors.job_url?.message}
          {...register("job_url")}
        />

        <div style={{ marginBottom: "1rem" }}>
          <label
            htmlFor="new-app-status"
            style={{
              display: "block",
              marginBottom: "0.25rem",
              fontSize: "0.875rem",
              fontWeight: 500,
              color: colors.textSecondary,
            }}
          >
            Initial Status
          </label>
          <select
            id="new-app-status"
            style={{
              width: "100%",
              padding: "0.5rem 0.75rem",
              border: `1px solid ${colors.border}`,
              borderRadius: "0.375rem",
              fontSize: "0.875rem",
              backgroundColor: colors.bgCard,
              boxSizing: "border-box",
            }}
            {...register("status")}
          >
            {APPLICATION_STATUSES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>

        <hr
          style={{
            border: "none",
            borderTop: `1px solid ${colors.borderLight}`,
            margin: "1.5rem 0",
          }}
        />
        <p
          style={{
            fontSize: "0.75rem",
            color: colors.textPlaceholder,
            marginBottom: "1rem",
          }}
        >
          Optional details
        </p>

        <div style={{ display: "flex", gap: "0.75rem" }}>
          <FormInput
            label="Salary Min"
            type="number"
            placeholder="50000"
            error={errors.salary_min?.message}
            {...register("salary_min")}
          />
          <FormInput
            label="Salary Max"
            type="number"
            placeholder="80000"
            error={errors.salary_max?.message}
            {...register("salary_max")}
          />
          <FormInput
            label="Currency"
            type="text"
            placeholder="EUR"
            error={errors.salary_currency?.message}
            {...register("salary_currency")}
          />
        </div>

        <FormInput
          label="Contact Name"
          type="text"
          placeholder="e.g. Jane Recruiter"
          error={errors.contact_name?.message}
          {...register("contact_name")}
        />
        <FormInput
          label="Contact Email"
          type="email"
          placeholder="jane@company.com"
          error={errors.contact_email?.message}
          {...register("contact_email")}
        />

        <div style={{ marginBottom: "1rem" }}>
          <label
            htmlFor="new-app-notes"
            style={{
              display: "block",
              marginBottom: "0.25rem",
              fontSize: "0.875rem",
              fontWeight: 500,
              color: colors.textSecondary,
            }}
          >
            Notes
          </label>
          <textarea
            id="new-app-notes"
            rows={3}
            placeholder="Any initial notes about this opportunity..."
            style={{
              width: "100%",
              padding: "0.5rem 0.75rem",
              border: `1px solid ${colors.border}`,
              borderRadius: "0.375rem",
              fontSize: "0.875rem",
              resize: "vertical",
              boxSizing: "border-box",
              fontFamily: "inherit",
            }}
            {...register("notes")}
          />
        </div>

        <Button
          type="submit"
          loading={isSubmitting}
          style={{ width: "100%", marginTop: "0.5rem" }}
        >
          Create Application
        </Button>
      </form>
    </div>
  );
}