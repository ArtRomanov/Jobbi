import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link } from "react-router-dom";
import { apiClient, handleApiError } from "@/shared/api";
import { FormInput, Button, useToast, colors, AuthLayout, PageHeader } from "@/shared/ui";
import { forgotPasswordSchema, type ForgotPasswordFormData } from "../model/schemas";

/**
 * Forgot Password page — lets the user request a password reset link.
 * This is a public route (no auth required).
 */
export function ForgotPasswordPage() {
  const { showToast } = useToast();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ForgotPasswordFormData>({
    resolver: zodResolver(forgotPasswordSchema),
  });

  const onSubmit = async (data: ForgotPasswordFormData) => {
    setIsSubmitting(true);
    try {
      await apiClient.post("/api/v1/auth/forgot-password", {
        email: data.email,
      });
      setIsSubmitted(true);
    } catch (error: unknown) {
      handleApiError(error, showToast);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AuthLayout>
      <PageHeader
        title="Forgot password"
        subtitle="Enter your email and we'll send you a reset link."
      />

      {isSubmitted ? (
        <div
          style={{
            padding: "1rem",
            backgroundColor: "#f0fdf4",
            border: "1px solid #bbf7d0",
            borderRadius: "0.375rem",
            fontSize: "0.875rem",
            color: "#166534",
            lineHeight: 1.5,
          }}
        >
          If an account with that email exists, we've sent a password reset
          link.
        </div>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)}>
          <FormInput
            label="Email"
            type="email"
            error={errors.email?.message}
            {...register("email")}
          />

          <Button
            type="submit"
            loading={isSubmitting}
            style={{ width: "100%", marginTop: "0.5rem" }}
          >
            Send Reset Link
          </Button>
        </form>
      )}

      <p
        style={{
          textAlign: "center",
          marginTop: "1.5rem",
          fontSize: "0.875rem",
          color: colors.textMuted,
        }}
      >
        <Link
          to="/login"
          style={{ color: colors.primary, textDecoration: "none" }}
        >
          Back to login
        </Link>
      </p>
    </AuthLayout>
  );
}
