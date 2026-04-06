import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { Cv } from "@/entities/cv";
import { FormInput, FormTextarea, Button, Divider, colors } from "@/shared/ui";
import { cvFormSchema, type CvFormValues } from "../model/schemas";
import { EMPTY_WORK_EXPERIENCE, EMPTY_EDUCATION } from "../lib/constants";

interface CvEditorFormProps {
  initialData?: Cv;
  onSave: (data: CvFormValues) => Promise<void>;
  isSaving: boolean;
}

function toFormDefaults(cv?: Cv): CvFormValues {
  if (!cv) {
    return {
      name: "",
      personal_info: {
        full_name: "",
        email: "",
        phone: "",
        location: "",
        linkedin_url: "",
      },
      summary: "",
      work_experience: [],
      education: [],
      skills: "",
      languages: "",
    };
  }

  return {
    name: cv.name,
    personal_info: {
      full_name: cv.personal_info?.full_name ?? "",
      email: cv.personal_info?.email ?? "",
      phone: cv.personal_info?.phone ?? "",
      location: cv.personal_info?.location ?? "",
      linkedin_url: cv.personal_info?.linkedin_url ?? "",
    },
    summary: cv.summary ?? "",
    work_experience: (cv.work_experience ?? []).map((w) => ({
      company: w.company,
      role: w.role,
      start_date: w.start_date ?? "",
      end_date: w.end_date ?? "",
      is_current: w.is_current,
      description: w.description ?? "",
    })),
    education: (cv.education ?? []).map((e) => ({
      institution: e.institution,
      degree: e.degree ?? "",
      field_of_study: e.field_of_study ?? "",
      start_year: e.start_year ?? "",
      end_year: e.end_year ?? "",
      description: e.description ?? "",
    })),
    skills: cv.skills ?? "",
    languages: cv.languages ?? "",
  };
}

/**
 * CV editor form with dynamic sections for work experience and education.
 * This is a `feature/` because it encapsulates a user interaction (creating
 * and editing a CV), not just entity display.
 */
export function CvEditorForm({
  initialData,
  onSave,
  isSaving,
}: CvEditorFormProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<CvFormValues>({
    resolver: zodResolver(cvFormSchema),
    defaultValues: toFormDefaults(initialData),
  });

  const {
    fields: workFields,
    append: appendWork,
    remove: removeWork,
  } = useFieldArray({ control, name: "work_experience" });

  const {
    fields: eduFields,
    append: appendEdu,
    remove: removeEdu,
  } = useFieldArray({ control, name: "education" });

  return (
    <form onSubmit={handleSubmit(onSave)}>
      <FormInput
        label="CV Name"
        error={errors.name?.message}
        {...register("name")}
      />

      <Divider label="Personal Information" />

      <FormInput
        label="Full Name"
        {...register("personal_info.full_name")}
      />

      <div style={{ display: "flex", gap: "0.75rem" }}>
        <div style={{ flex: 1 }}>
          <FormInput
            label="Email"
            type="email"
            {...register("personal_info.email")}
          />
        </div>
        <div style={{ flex: 1 }}>
          <FormInput
            label="Phone"
            {...register("personal_info.phone")}
          />
        </div>
      </div>

      <FormInput
        label="Location"
        {...register("personal_info.location")}
      />

      <FormInput
        label="LinkedIn URL"
        type="url"
        {...register("personal_info.linkedin_url")}
      />

      <Divider label="Summary" />

      <FormTextarea
        label="Professional Summary"
        rows={4}
        {...register("summary")}
      />

      <Divider label="Work Experience" />

      {workFields.map((field, index) => (
        <div
          key={field.id}
          style={{
            padding: "1rem",
            marginBottom: "1rem",
            border: `1px solid ${colors.borderLight}`,
            borderRadius: "0.375rem",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "0.5rem",
            }}
          >
            <span
              style={{
                fontSize: "0.8125rem",
                fontWeight: 600,
                color: colors.textSecondary,
              }}
            >
              Experience {index + 1}
            </span>
            <button
              type="button"
              onClick={() => removeWork(index)}
              style={{
                background: "none",
                border: "none",
                color: colors.error,
                cursor: "pointer",
                fontSize: "0.8125rem",
              }}
            >
              Remove
            </button>
          </div>

          <div style={{ display: "flex", gap: "0.75rem" }}>
            <div style={{ flex: 1 }}>
              <FormInput
                label="Company"
                error={errors.work_experience?.[index]?.company?.message}
                {...register(`work_experience.${index}.company`)}
              />
            </div>
            <div style={{ flex: 1 }}>
              <FormInput
                label="Role"
                error={errors.work_experience?.[index]?.role?.message}
                {...register(`work_experience.${index}.role`)}
              />
            </div>
          </div>

          <div style={{ display: "flex", gap: "0.75rem" }}>
            <div style={{ flex: 1 }}>
              <FormInput
                label="Start Date"
                placeholder="YYYY-MM"
                {...register(`work_experience.${index}.start_date`)}
              />
            </div>
            <div style={{ flex: 1 }}>
              <FormInput
                label="End Date"
                placeholder="YYYY-MM"
                {...register(`work_experience.${index}.end_date`)}
              />
            </div>
          </div>

          <div style={{ marginBottom: "1rem" }}>
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                fontSize: "0.875rem",
                color: colors.textSecondary,
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                {...register(`work_experience.${index}.is_current`)}
              />
              Currently working here
            </label>
          </div>

          <FormTextarea
            label="Description"
            rows={3}
            {...register(`work_experience.${index}.description`)}
          />
        </div>
      ))}

      <Button
        type="button"
        variant="secondary"
        onClick={() => appendWork(EMPTY_WORK_EXPERIENCE)}
        style={{ marginBottom: "1rem" }}
      >
        + Add Work Experience
      </Button>

      <Divider label="Education" />

      {eduFields.map((field, index) => (
        <div
          key={field.id}
          style={{
            padding: "1rem",
            marginBottom: "1rem",
            border: `1px solid ${colors.borderLight}`,
            borderRadius: "0.375rem",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "0.5rem",
            }}
          >
            <span
              style={{
                fontSize: "0.8125rem",
                fontWeight: 600,
                color: colors.textSecondary,
              }}
            >
              Education {index + 1}
            </span>
            <button
              type="button"
              onClick={() => removeEdu(index)}
              style={{
                background: "none",
                border: "none",
                color: colors.error,
                cursor: "pointer",
                fontSize: "0.8125rem",
              }}
            >
              Remove
            </button>
          </div>

          <FormInput
            label="Institution"
            error={errors.education?.[index]?.institution?.message}
            {...register(`education.${index}.institution`)}
          />

          <div style={{ display: "flex", gap: "0.75rem" }}>
            <div style={{ flex: 1 }}>
              <FormInput
                label="Degree"
                {...register(`education.${index}.degree`)}
              />
            </div>
            <div style={{ flex: 1 }}>
              <FormInput
                label="Field of Study"
                {...register(`education.${index}.field_of_study`)}
              />
            </div>
          </div>

          <div style={{ display: "flex", gap: "0.75rem" }}>
            <div style={{ flex: 1 }}>
              <FormInput
                label="Start Year"
                placeholder="YYYY"
                {...register(`education.${index}.start_year`)}
              />
            </div>
            <div style={{ flex: 1 }}>
              <FormInput
                label="End Year"
                placeholder="YYYY"
                {...register(`education.${index}.end_year`)}
              />
            </div>
          </div>

          <FormTextarea
            label="Description"
            rows={3}
            {...register(`education.${index}.description`)}
          />
        </div>
      ))}

      <Button
        type="button"
        variant="secondary"
        onClick={() => appendEdu(EMPTY_EDUCATION)}
        style={{ marginBottom: "1rem" }}
      >
        + Add Education
      </Button>

      <Divider label="Skills & Languages" />

      <FormTextarea
        label="Skills"
        rows={3}
        placeholder="e.g. JavaScript, React, TypeScript, Node.js"
        {...register("skills")}
      />

      <FormTextarea
        label="Languages"
        rows={2}
        placeholder="e.g. English (Native), Spanish (Intermediate)"
        {...register("languages")}
      />

      <div style={{ marginTop: "1.5rem" }}>
        <Button type="submit" loading={isSaving}>
          Save CV
        </Button>
      </div>
    </form>
  );
}
