import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useNavigate } from "react-router-dom";
import { apiClient, handleApiError } from "@/shared/api";
import {
  FormInput,
  FormSelect,
  Button,
  useToast,
  colors,
  AuthLayout,
  PageHeader,
  Divider,
} from "@/shared/ui";
import { useAuthStore } from "@/features/auth";

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

const REMOTE_OPTIONS = [
  { value: "", label: "Select..." },
  { value: "onsite", label: "Onsite" },
  { value: "remote", label: "Remote" },
  { value: "hybrid", label: "Hybrid" },
];

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
      handleApiError(error, showToast, {
        409: "An account with this email already exists.",
        422: "Please check your input and try again.",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AuthLayout maxWidth="480px">
      <PageHeader
        title="Create your Jobbi account"
        subtitle="Start tracking your job applications"
      />

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

        <Divider label="Optional — helps us tailor your experience" />

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
          color: colors.textMuted,
        }}
      >
        Already have an account?{" "}
        <Link
          to="/login"
          style={{ color: colors.primary, textDecoration: "none" }}
        >
          Log in
        </Link>
      </p>
    </AuthLayout>
  );
}
