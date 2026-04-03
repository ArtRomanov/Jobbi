import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import { apiClient, isApiError } from "@/shared/api";
import { FormInput, Button, useToast, colors, fonts } from "@/shared/ui";

const resetPasswordSchema = z
  .object({
    password: z.string().min(8, "Password must be at least 8 characters"),
    confirmPassword: z.string().min(1, "Please confirm your password"),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

type ResetPasswordFormData = z.infer<typeof resetPasswordSchema>;

/**
 * Reset Password page — lets the user set a new password using a token from their email.
 * Reads the `token` query param from the URL. This is a public route (no auth required).
 */
export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [expiredError, setExpiredError] = useState(false);

  const token = searchParams.get("token");

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ResetPasswordFormData>({
    resolver: zodResolver(resetPasswordSchema),
  });

  const onSubmit = async (data: ResetPasswordFormData) => {
    if (!token) return;

    setIsSubmitting(true);
    setExpiredError(false);
    try {
      await apiClient.post("/api/v1/auth/reset-password", {
        token,
        new_password: data.password,
      });
      showToast("Password reset successfully. Please log in.", "success");
      navigate("/login");
    } catch (error: unknown) {
      if (isApiError(error) && error.status === 400) {
        setExpiredError(true);
      } else if (isApiError(error)) {
        showToast("Something went wrong. Please try again.", "error");
      } else {
        showToast("Network error. Check your connection.", "error");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const hasToken = token !== null && token.length > 0;

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
          Reset password
        </h1>
        <p
          style={{
            fontSize: "0.875rem",
            color: colors.textMuted,
            marginBottom: "1.5rem",
          }}
        >
          {hasToken
            ? "Enter your new password below."
            : "This reset link is not valid."}
        </p>

        {!hasToken ? (
          <div
            style={{
              padding: "1rem",
              backgroundColor: "#fef2f2",
              border: "1px solid #fecaca",
              borderRadius: "0.375rem",
              fontSize: "0.875rem",
              color: "#991b1b",
              lineHeight: 1.5,
            }}
          >
            Invalid reset link.
          </div>
        ) : (
          <>
            {expiredError ? (
              <div
                style={{
                  padding: "1rem",
                  marginBottom: "1rem",
                  backgroundColor: "#fef2f2",
                  border: "1px solid #fecaca",
                  borderRadius: "0.375rem",
                  fontSize: "0.875rem",
                  color: "#991b1b",
                  lineHeight: 1.5,
                }}
              >
                This reset link has expired. Please{" "}
                <Link
                  to="/forgot-password"
                  style={{ color: "#991b1b", fontWeight: 500 }}
                >
                  request a new one
                </Link>
                .
              </div>
            ) : null}

            <form onSubmit={handleSubmit(onSubmit)}>
              <FormInput
                label="New Password"
                type="password"
                error={errors.password?.message}
                {...register("password")}
              />
              <FormInput
                label="Confirm Password"
                type="password"
                error={errors.confirmPassword?.message}
                {...register("confirmPassword")}
              />

              <Button
                type="submit"
                loading={isSubmitting}
                style={{ width: "100%", marginTop: "0.5rem" }}
              >
                Reset Password
              </Button>
            </form>
          </>
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
