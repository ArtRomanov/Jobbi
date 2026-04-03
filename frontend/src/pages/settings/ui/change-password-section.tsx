import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { apiClient, handleApiError } from "@/shared/api";
import { FormInput, Button, useToast, colors } from "@/shared/ui";

const changePasswordSchema = z.object({
  current_password: z.string().min(1, "Current password is required"),
  new_password: z.string().min(8, "New password must be at least 8 characters"),
});

type ChangePasswordFormData = z.infer<typeof changePasswordSchema>;

export function ChangePasswordSection() {
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
      handleApiError(error, showToast, {
        400: "Current password is incorrect.",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <hr
        style={{
          border: "none",
          borderTop: `1px solid ${colors.borderLight}`,
          margin: "2rem 0",
        }}
      />

      <h2
        style={{
          fontSize: "1.25rem",
          fontWeight: 700,
          marginBottom: "0.25rem",
          color: colors.textPrimary,
        }}
      >
        Change Password
      </h2>
      <p
        style={{
          fontSize: "0.875rem",
          color: colors.textMuted,
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
