import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useNavigate } from "react-router-dom";
import { apiClient, handleApiError } from "@/shared/api";
import { FormInput, Button, useToast, colors, AuthLayout, PageHeader } from "@/shared/ui";
import { useAuthStore } from "@/features/auth";

const loginSchema = z.object({
  email: z.string().email("Invalid email address"),
  password: z.string().min(1, "Password is required"),
});

type LoginFormData = z.infer<typeof loginSchema>;

interface LoginResponse {
  access_token: string;
  token_type: string;
  user: {
    id: string;
    email: string;
    full_name: string;
  };
}

export function LoginPage() {
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);
  const { showToast } = useToast();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (data: LoginFormData) => {
    setIsSubmitting(true);
    try {
      const response = await apiClient.post<LoginResponse>(
        "/api/v1/auth/login",
        data,
      );
      login(response.access_token);
      navigate("/dashboard");
    } catch (error: unknown) {
      handleApiError(error, showToast, {
        401: "Invalid email or password.",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AuthLayout>
      <PageHeader title="Welcome back" subtitle="Sign in to your Jobbi account" />

      <form onSubmit={handleSubmit(onSubmit)}>
        <FormInput
          label="Email"
          type="email"
          error={errors.email?.message}
          {...register("email")}
        />
        <FormInput
          label="Password"
          type="password"
          error={errors.password?.message}
          {...register("password")}
        />

        <div style={{ textAlign: "right", marginBottom: "0.5rem" }}>
          <Link
            to="/forgot-password"
            style={{
              fontSize: "0.8125rem",
              color: colors.primary,
              textDecoration: "none",
            }}
          >
            Forgot password?
          </Link>
        </div>

        <Button
          type="submit"
          loading={isSubmitting}
          style={{ width: "100%", marginTop: "0.5rem" }}
        >
          Sign In
        </Button>
      </form>

      <p
        style={{
          textAlign: "center",
          marginTop: "1.5rem",
          fontSize: "0.875rem",
          color: colors.textMuted,
        }}
      >
        Don't have an account?{" "}
        <Link
          to="/register"
          style={{ color: colors.primary, textDecoration: "none" }}
        >
          Sign up
        </Link>
      </p>
    </AuthLayout>
  );
}
