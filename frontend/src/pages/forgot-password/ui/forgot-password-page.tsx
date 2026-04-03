import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link } from "react-router-dom";
import { apiClient, isApiError } from "@/shared/api";
import { FormInput, Button, useToast, colors, fonts } from "@/shared/ui";

const forgotPasswordSchema = z.object({
  email: z.string().email("Invalid email address"),
});

type ForgotPasswordFormData = z.infer<typeof forgotPasswordSchema>;

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
      if (isApiError(error)) {
        showToast("Something went wrong. Please try again.", "error");
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
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: colors.bgPage,
        fontFamily: fonts.base,
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "400px",
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
          Forgot password
        </h1>
        <p
          style={{
            fontSize: "0.875rem",
            color: colors.textMuted,
            marginBottom: "1.5rem",
          }}
        >
          Enter your email and we'll send you a reset link.
        </p>

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
      </div>
    </div>
  );
}
