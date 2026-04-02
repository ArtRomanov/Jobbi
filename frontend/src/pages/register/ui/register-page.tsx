import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useNavigate } from "react-router-dom";
import { apiClient, isApiError } from "@/shared/api";
import { FormInput, Button, useToast } from "@/shared/ui";
import { useAuthStore } from "@/features/auth";

const RemotePreference = {
  Onsite: "onsite",
  Remote: "remote",
  Hybrid: "hybrid",
} as const;

type RemotePreference = (typeof RemotePreference)[keyof typeof RemotePreference];

const registerSchema = z.object({
  full_name: z.string().min(1, "Full name is required"),
  email: z.string().email("Invalid email address"),
  password: z.string().min(8, "Password must be at least 8 characters"),
  desired_role: z.string().optional(),
  desired_location: z.string().optional(),
  remote_preference: z
    .enum(["onsite", "remote", "hybrid"])
    .optional(),
  salary_min: z.string().optional(),
  salary_max: z.string().optional(),
  salary_currency: z.string().optional(),
});

type RegisterFormData = z.infer<typeof registerSchema>;

interface RegisterResponse {
  access_token: string;
  token_type: string;
  user: {
    id: string;
    email: string;
    full_name: string;
  };
}

export function RegisterPage() {
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);
  const { showToast } = useToast();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
  });

  const onSubmit = async (data: RegisterFormData) => {
    setIsSubmitting(true);
    try {
      // Clean up empty optional fields before sending to API
      const body = {
        full_name: data.full_name,
        email: data.email,
        password: data.password,
        ...(data.desired_role ? { desired_role: data.desired_role } : {}),
        ...(data.desired_location
          ? { desired_location: data.desired_location }
          : {}),
        ...(data.remote_preference
          ? { remote_preference: data.remote_preference }
          : {}),
        ...(data.salary_min ? { salary_min: Number(data.salary_min) } : {}),
        ...(data.salary_max ? { salary_max: Number(data.salary_max) } : {}),
        ...(data.salary_currency
          ? { salary_currency: data.salary_currency }
          : {}),
      };

      const response = await apiClient.post<RegisterResponse>(
        "/api/v1/auth/register",
        body,
      );
      login(response.access_token);
      navigate("/dashboard");
    } catch (error: unknown) {
      if (isApiError(error) && error.status === 409) {
        showToast("An account with this email already exists.", "error");
      } else if (isApiError(error) && error.status === 422) {
        showToast("Please check your input and try again.", "error");
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
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: "#fafafa",
        fontFamily:
          "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "480px",
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
          Create your Jobbi account
        </h1>
        <p
          style={{
            fontSize: "0.875rem",
            color: "#6b7280",
            marginBottom: "1.5rem",
          }}
        >
          Start tracking your job applications
        </p>

        <form onSubmit={handleSubmit(onSubmit)}>
          <FormInput
            label="Full Name *"
            type="text"
            error={errors.full_name?.message}
            {...register("full_name")}
          />
          <FormInput
            label="Email *"
            type="email"
            error={errors.email?.message}
            {...register("email")}
          />
          <FormInput
            label="Password *"
            type="password"
            error={errors.password?.message}
            {...register("password")}
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
            Optional — helps us tailor your experience
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
              <option value={RemotePreference.Onsite}>Onsite</option>
              <option value={RemotePreference.Remote}>Remote</option>
              <option value={RemotePreference.Hybrid}>Hybrid</option>
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
            loading={isSubmitting}
            style={{ width: "100%", marginTop: "0.5rem" }}
          >
            Create Account
          </Button>
        </form>

        <p
          style={{
            textAlign: "center",
            marginTop: "1.5rem",
            fontSize: "0.875rem",
            color: "#6b7280",
          }}
        >
          Already have an account?{" "}
          <Link
            to="/login"
            style={{ color: "#2563eb", textDecoration: "none" }}
          >
            Log in
          </Link>
        </p>
      </div>
    </div>
  );
}
