import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { apiClient, isApiError } from "@/shared/api";
import { FormInput, Button, useToast } from "@/shared/ui";
import { getMe, updateMe } from "@/entities/user";
import type { User } from "@/entities/user";

const changePasswordSchema = z.object({
  current_password: z.string().min(1, "Current password is required"),
  new_password: z.string().min(8, "New password must be at least 8 characters"),
});

type ChangePasswordFormData = z.infer<typeof changePasswordSchema>;

const settingsSchema = z.object({
  full_name: z.string().min(1, "Full name is required"),
  desired_role: z.string().optional(),
  desired_location: z.string().optional(),
  remote_preference: z.enum(["onsite", "remote", "hybrid", ""]).optional(),
  salary_min: z.string().optional(),
  salary_max: z.string().optional(),
  salary_currency: z.string().optional(),
});

type SettingsFormData = z.infer<typeof settingsSchema>;

/** Convert user API data to form field values. */
function userToFormValues(user: User): SettingsFormData {
  return {
    full_name: user.full_name,
    desired_role: user.desired_role ?? "",
    desired_location: user.desired_location ?? "",
    remote_preference: (user.remote_preference as SettingsFormData["remote_preference"]) ?? "",
    salary_min: user.salary_min !== null ? String(user.salary_min) : "",
    salary_max: user.salary_max !== null ? String(user.salary_max) : "",
    salary_currency: user.salary_currency ?? "",
  };
}

export function SettingsPage() {
  const { showToast } = useToast();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, dirtyFields },
  } = useForm<SettingsFormData>({
    resolver: zodResolver(settingsSchema),
  });

  useEffect(() => {
    let cancelled = false;

    async function fetchUser(): Promise<void> {
      try {
        const data = await getMe();
        if (cancelled) return;
        setUser(data);
        reset(userToFormValues(data));
      } catch (error: unknown) {
        if (cancelled) return;
        if (isApiError(error)) {
          showToast("Failed to load profile.", "error");
        } else {
          showToast("Network error. Check your connection.", "error");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    void fetchUser();
    return () => { cancelled = true; };
  }, [reset, showToast]);

  const onSubmit = async (data: SettingsFormData) => {
    if (isSaving) return;
    // Only send fields the user actually changed (exclude_unset pattern)
    const changed: Record<string, unknown> = {};
    for (const key of Object.keys(dirtyFields) as Array<keyof SettingsFormData>) {
      const value = data[key];
      if (key === "salary_min" || key === "salary_max") {
        changed[key] = value ? Number(value) : null;
      } else {
        changed[key] = value || null;
      }
    }

    // Nothing changed — skip the request
    if (Object.keys(changed).length === 0) {
      showToast("No changes to save.", "success");
      return;
    }

    setIsSaving(true);
    try {
      const updated = await updateMe(changed);
      setUser(updated);
      reset(userToFormValues(updated));
      showToast("Profile updated.", "success");
    } catch (error: unknown) {
      if (isApiError(error) && error.status === 422) {
        showToast("Please check your input and try again.", "error");
      } else if (isApiError(error)) {
        showToast("Failed to save changes.", "error");
      } else {
        showToast("Network error. Check your connection.", "error");
      }
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div
        role="status"
        aria-live="polite"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "60vh",
          color: "#6b7280",
          fontSize: "0.875rem",
        }}
      >
        Loading profile...
      </div>
    );
  }

  if (!user) {
    return (
      <div
        role="alert"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "60vh",
          color: "#ef4444",
          fontSize: "0.875rem",
        }}
      >
        Could not load profile. Please try refreshing the page.
      </div>
    );
  }

  return (
    <div
      style={{
        maxWidth: "480px",
        margin: "2rem auto",
        padding: "2rem",
        backgroundColor: "#ffffff",
        borderRadius: "0.5rem",
        boxShadow: "0 1px 3px rgba(0, 0, 0, 0.1)",
      }}
    >
      <h1
        style={{
          fontSize: "1.5rem",
          fontWeight: 700,
          marginBottom: "0.25rem",
          color: "#1a1a1a",
        }}
      >
        Profile Settings
      </h1>
      <p
        style={{
          fontSize: "0.875rem",
          color: "#6b7280",
          marginBottom: "1.5rem",
        }}
      >
        Update your profile information
      </p>

      <form onSubmit={handleSubmit(onSubmit)}>
        {/* Email is read-only — displayed but not editable */}
        <div style={{ marginBottom: "1rem" }}>
          <label
            htmlFor="settings-email"
            style={{
              display: "block",
              marginBottom: "0.25rem",
              fontSize: "0.875rem",
              fontWeight: 500,
              color: "#374151",
            }}
          >
            Email
          </label>
          <input
            id="settings-email"
            type="email"
            value={user.email}
            readOnly
            style={{
              width: "100%",
              padding: "0.5rem 0.75rem",
              border: "1px solid #d1d5db",
              borderRadius: "0.375rem",
              fontSize: "0.875rem",
              backgroundColor: "#f3f4f6",
              color: "#6b7280",
              boxSizing: "border-box",
              cursor: "not-allowed",
            }}
          />
        </div>

        <FormInput
          label="Full Name *"
          type="text"
          error={errors.full_name?.message}
          {...register("full_name")}
        />

        <hr
          style={{
            border: "none",
            borderTop: "1px solid #e5e7eb",
            margin: "1.5rem 0",
          }}
        />
        <p
          style={{
            fontSize: "0.75rem",
            color: "#9ca3af",
            marginBottom: "1rem",
          }}
        >
          Job preferences
        </p>

        <FormInput
          label="Desired Role"
          type="text"
          placeholder="e.g. Frontend Developer"
          error={errors.desired_role?.message}
          {...register("desired_role")}
        />
        <FormInput
          label="Desired Location"
          type="text"
          placeholder="e.g. Berlin, Germany"
          error={errors.desired_location?.message}
          {...register("desired_location")}
        />

        <div style={{ marginBottom: "1rem" }}>
          <label
            htmlFor="settings-remote-preference"
            style={{
              display: "block",
              marginBottom: "0.25rem",
              fontSize: "0.875rem",
              fontWeight: 500,
              color: "#374151",
            }}
          >
            Remote Preference
          </label>
          <select
            id="settings-remote-preference"
            style={{
              width: "100%",
              padding: "0.5rem 0.75rem",
              border: "1px solid #d1d5db",
              borderRadius: "0.375rem",
              fontSize: "0.875rem",
              backgroundColor: "#ffffff",
              boxSizing: "border-box",
            }}
            {...register("remote_preference")}
          >
            <option value="">Select...</option>
            <option value="onsite">Onsite</option>
            <option value="remote">Remote</option>
            <option value="hybrid">Hybrid</option>
          </select>
        </div>

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

        <Button
          type="submit"
          loading={isSaving}
          style={{ width: "100%", marginTop: "0.5rem" }}
        >
          Save Changes
        </Button>
      </form>

      <ChangePasswordSection />
    </div>
  );
}

function ChangePasswordSection() {
  const { showToast } = useToast();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ChangePasswordFormData>({
    resolver: zodResolver(changePasswordSchema),
  });

  const onSubmit = async (data: ChangePasswordFormData) => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      await apiClient.post("/api/v1/users/me/change-password", {
        current_password: data.current_password,
        new_password: data.new_password,
      });
      showToast("Password changed successfully.", "success");
      reset();
    } catch (error: unknown) {
      if (isApiError(error) && error.status === 400) {
        showToast("Current password is incorrect.", "error");
      } else if (isApiError(error)) {
        showToast("Something went wrong. Please try again.", "error");
      } else {
        showToast("Network error. Check your connection.", "error");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <hr
        style={{
          border: "none",
          borderTop: "1px solid #e5e7eb",
          margin: "2rem 0",
        }}
      />

      <h2
        style={{
          fontSize: "1.25rem",
          fontWeight: 700,
          marginBottom: "0.25rem",
          color: "#1a1a1a",
        }}
      >
        Change Password
      </h2>
      <p
        style={{
          fontSize: "0.875rem",
          color: "#6b7280",
          marginBottom: "1.5rem",
        }}
      >
        Update your account password
      </p>

      <form onSubmit={handleSubmit(onSubmit)}>
        <FormInput
          label="Current Password *"
          type="password"
          autoComplete="current-password"
          error={errors.current_password?.message}
          {...register("current_password")}
        />
        <FormInput
          label="New Password *"
          type="password"
          autoComplete="new-password"
          error={errors.new_password?.message}
          {...register("new_password")}
        />

        <Button
          type="submit"
          loading={isSubmitting}
          style={{ width: "100%", marginTop: "0.5rem" }}
        >
          Change Password
        </Button>
      </form>
    </>
  );
}
