import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { handleApiError } from "@/shared/api";
import {
  FormInput,
  FormSelect,
  Button,
  useToast,
  colors,
  PageCard,
  PageHeader,
  Divider,
} from "@/shared/ui";
import { TelegramSection } from "@/features/telegram-connect";
import { getMe, updateMe } from "@/entities/user";
import type { User } from "@/entities/user";
import { settingsSchema, type SettingsFormData } from "../model/schemas";
import { REMOTE_OPTIONS } from "../lib/constants";
import {
  detectBrowserTimezone,
  getTimezoneOptions,
  userToFormValues,
} from "../lib/helpers";
import { ChangePasswordSection } from "./change-password-section";

export function SettingsPage() {
  const { showToast } = useToast();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    formState: { errors, dirtyFields, isDirty },
  } = useForm<SettingsFormData>({
    resolver: zodResolver(settingsSchema),
  });

  useEffect(() => {
    let cancelled = false;

    async function fetchUser(): Promise<void> {
      try {
        const data = await getMe();
        if (cancelled) return;

        // Daily-summary scheduling needs a timezone: on first visit, detect and save it.
        const detectedTimezone = data.timezone ? null : detectBrowserTimezone();
        if (!detectedTimezone) {
          setUser(data);
          reset(userToFormValues(data));
          return;
        }

        try {
          const updated = await updateMe({ timezone: detectedTimezone });
          if (cancelled) return;
          setUser(updated);
          reset(userToFormValues(updated));
          showToast(`Timezone detected and saved: ${detectedTimezone}.`, "success");
        } catch {
          if (cancelled) return;
          // Auto-save failed: prefill as a dirty field so "Save Changes" persists it.
          setUser(data);
          reset(userToFormValues(data));
          setValue("timezone", detectedTimezone, { shouldDirty: true });
          showToast(
            `Detected timezone ${detectedTimezone} but couldn't save it. Click "Save Changes" to save.`,
            "error",
          );
        }
      } catch (error: unknown) {
        if (cancelled) return;
        handleApiError(error, showToast);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    void fetchUser();
    return () => { cancelled = true; };
  }, [reset, setValue, showToast]);

  const savedTimezone = user?.timezone ?? null;
  const timezoneOptions = useMemo(() => getTimezoneOptions(savedTimezone), [savedTimezone]);

  const onSubmit = async (data: SettingsFormData) => {
    // Save is soft-disabled (aria-disabled) while clean, so it can't submit
    if (isSaving || !isDirty) return;
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

    setIsSaving(true);
    try {
      const updated = await updateMe(changed);
      setUser(updated);
      reset(userToFormValues(updated));
      showToast("Profile updated.", "success");
    } catch (error: unknown) {
      handleApiError(error, showToast, {
        422: "Please check your input and try again.",
      });
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
          color: colors.textMuted,
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
          color: colors.error,
          fontSize: "0.875rem",
        }}
      >
        Could not load profile. Please try refreshing the page.
      </div>
    );
  }

  return (
    <PageCard>
      <PageHeader title="Profile Settings" subtitle="Update your profile information" />

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
              color: colors.textSecondary,
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
              border: `1px solid ${colors.border}`,
              borderRadius: "0.375rem",
              fontSize: "0.875rem",
              backgroundColor: colors.bgDisabled,
              color: colors.textMuted,
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

        <Divider label="Job preferences" />

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

        <FormSelect
          label="Remote Preference"
          options={REMOTE_OPTIONS}
          {...register("remote_preference")}
        />

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

        <Divider label="Telegram daily summary (sent at this time in your timezone)" />

        <FormSelect
          label="Timezone"
          options={timezoneOptions}
          error={errors.timezone?.message}
          {...register("timezone")}
        />
        <FormInput
          label="Daily Summary Time"
          type="time"
          error={errors.summary_time?.message}
          {...register("summary_time")}
        />

        {/* Off until a field differs from the saved profile; stays focusable
            (aria-disabled) so focus is not lost after a save */}
        <Button
          type="submit"
          loading={isSaving}
          disabled={!isDirty}
          keepFocusable
          style={{ width: "100%", marginTop: "0.5rem" }}
        >
          Save Changes
        </Button>
      </form>

      <TelegramSection />

      <ChangePasswordSection />
    </PageCard>
  );
}
