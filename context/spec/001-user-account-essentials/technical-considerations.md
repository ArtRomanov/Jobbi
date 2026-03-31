<!--
This document describes HOW to build the feature at an architectural level.
It is NOT a copy-paste implementation guide.
-->

# Technical Specification: User Account Essentials

- **Functional Specification:** `context/spec/001-user-account-essentials/functional-spec.md`
- **Status:** Draft
- **Author(s):** Poe (AI Technical Architect)

---

## 1. High-Level Technical Approach

This is the **first feature** built for Jobbi, so it establishes the entire project skeleton: backend (FastAPI), frontend (React + Vite), database (SQLite via SQLAlchemy), and Docker Compose orchestration.

The auth system uses **JWT access tokens** (7-day expiry) stored in the browser's local storage. Passwords are hashed with **bcrypt**. The forgot-password flow generates a one-time token and **logs the reset link to the console** (no email service in V1). The frontend uses **Feature-Sliced Design** with React Hook Form + Zod for form validation and a native fetch wrapper for API communication.

**Systems affected:** Everything is new — backend, frontend, database, Docker setup.

---

## 2. Proposed Solution & Implementation Plan

### 2.1 Project Structure

```
/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # Route handlers
│   │   ├── core/            # Config, security, dependencies
│   │   ├── models/          # SQLAlchemy models
│   │   ├── schemas/         # Pydantic request/response schemas
│   │   ├── services/        # Business logic
│   │   └── main.py          # FastAPI app entry point
│   ├── alembic/             # Database migrations
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app/             # FSD: app layer (router, providers)
│   │   ├── pages/           # FSD: page components
│   │   ├── features/        # FSD: feature slices
│   │   ├── entities/        # FSD: entity slices
│   │   └── shared/          # FSD: shared utilities, UI, API client
│   ├── Dockerfile
│   ├── package.json
│   └── vite.config.ts
├── docker-compose.yml
└── .env.example
```

### 2.2 Data Model / Database Changes

**Table: `users`**

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | Generated server-side |
| `email` | VARCHAR(255) | UNIQUE, NOT NULL | Used for login |
| `password_hash` | VARCHAR(255) | NOT NULL | bcrypt hash |
| `full_name` | VARCHAR(255) | NOT NULL | |
| `desired_role` | VARCHAR(255) | NULLABLE | Free text |
| `desired_location` | VARCHAR(255) | NULLABLE | Free text |
| `remote_preference` | VARCHAR(20) | NULLABLE | Enum: `onsite`, `remote`, `hybrid` |
| `salary_min` | INTEGER | NULLABLE | |
| `salary_max` | INTEGER | NULLABLE | |
| `salary_currency` | VARCHAR(3) | NULLABLE | ISO 4217 code (e.g., `USD`, `EUR`) |
| `created_at` | DATETIME | NOT NULL | Auto-set on creation |
| `updated_at` | DATETIME | NOT NULL | Auto-updated on change |

**Table: `password_reset_tokens`**

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `user_id` | UUID | FK → users.id, NOT NULL | |
| `token_hash` | VARCHAR(255) | NOT NULL | SHA-256 hash of the token (never store raw) |
| `expires_at` | DATETIME | NOT NULL | Created + 1 hour |
| `used_at` | DATETIME | NULLABLE | Set when token is consumed; prevents reuse |

**Migration:** Initial Alembic migration creates both tables.

### 2.3 API Contracts

**Auth Routes** (no authentication required):

**`POST /api/v1/auth/register`**
- Request: `{ email, password, full_name, desired_role?, desired_location?, remote_preference?, salary_min?, salary_max?, salary_currency? }`
- Success (201): `{ access_token, token_type: "bearer", user: { id, email, full_name, ... } }`
- Error (409): `{ detail: "An account with this email already exists." }`
- Error (422): Validation errors (email format, password length)

**`POST /api/v1/auth/login`**
- Request: `{ email, password }`
- Success (200): `{ access_token, token_type: "bearer", user: { id, email, full_name, ... } }`
- Error (401): `{ detail: "Invalid email or password." }`

**`POST /api/v1/auth/forgot-password`**
- Request: `{ email }`
- Success (200): `{ message: "If an account with that email exists, we've sent a password reset link." }` (always 200, even if email not found)
- Side effect: Logs reset link to console if email exists

**`POST /api/v1/auth/reset-password`**
- Request: `{ token, new_password }`
- Success (200): `{ message: "Password reset successfully." }`
- Error (400): `{ detail: "This reset link has expired. Please request a new one." }`

**User Routes** (JWT required):

**`GET /api/v1/users/me`**
- Success (200): `{ id, email, full_name, desired_role, desired_location, remote_preference, salary_min, salary_max, salary_currency, created_at }`

**`PATCH /api/v1/users/me`**
- Request: `{ full_name?, desired_role?, desired_location?, remote_preference?, salary_min?, salary_max?, salary_currency? }`
- Success (200): Updated user object
- Note: `email` is NOT editable via this endpoint

**`POST /api/v1/users/me/change-password`**
- Request: `{ current_password, new_password }`
- Success (200): `{ message: "Password changed successfully." }`
- Error (400): `{ detail: "Current password is incorrect." }`

**`POST /api/v1/auth/logout`**
- Success (200): `{ message: "Logged out." }`
- Note: Logout is primarily client-side (clear JWT from local storage). This endpoint exists for future server-side token invalidation.

### 2.4 Backend Components

| Path | Responsibility |
|---|---|
| `backend/app/core/config.py` | App settings via Pydantic Settings (SECRET_KEY, DB URL, token expiry) |
| `backend/app/core/security.py` | JWT creation/verification, bcrypt hashing, password reset token generation |
| `backend/app/core/deps.py` | FastAPI dependencies (get_db session, get_current_user from JWT) |
| `backend/app/models/user.py` | SQLAlchemy `User` model |
| `backend/app/models/password_reset.py` | SQLAlchemy `PasswordResetToken` model |
| `backend/app/schemas/auth.py` | Pydantic schemas for register, login, reset requests/responses |
| `backend/app/schemas/user.py` | Pydantic schemas for user profile read/update |
| `backend/app/api/v1/auth.py` | Auth route handlers (register, login, forgot/reset password, logout) |
| `backend/app/api/v1/users.py` | User route handlers (get/update profile, change password) |
| `backend/app/services/auth_service.py` | Auth business logic (create user, verify credentials, generate reset token) |
| `backend/app/main.py` | FastAPI app factory, CORS config, router mounting, Sentry init, structlog setup |

### 2.5 Frontend Components (FSD)

| Layer/Slice | Path | Content |
|---|---|---|
| `shared/api` | `frontend/src/shared/api/` | Fetch wrapper with JWT interceptor, base URL config |
| `shared/ui` | `frontend/src/shared/ui/` | Form input, button, toast, layout components |
| `entities/user` | `frontend/src/entities/user/` | User types, `GET /users/me` API call, user store (Zustand) |
| `features/auth` | `frontend/src/features/auth/` | Login form, register form, forgot password form, reset password form, auth Zustand store (token, isAuthenticated, login/logout actions) |
| `pages/login` | `frontend/src/pages/login/` | Login page composing `features/auth` login form |
| `pages/register` | `frontend/src/pages/register/` | Registration page composing `features/auth` register form |
| `pages/forgot-password` | `frontend/src/pages/forgot-password/` | Forgot password page |
| `pages/reset-password` | `frontend/src/pages/reset-password/` | Reset password page (reads token from URL) |
| `pages/settings` | `frontend/src/pages/settings/` | Profile management + change password sections |
| `app/router` | `frontend/src/app/router/` | Route definitions, `ProtectedRoute` wrapper (redirects to /login if not authed) |
| `app/providers` | `frontend/src/app/providers/` | QueryClient provider, theme provider |

### 2.6 Configuration

| Env Variable | Purpose | Example |
|---|---|---|
| `SECRET_KEY` | JWT signing key | Random 32+ char string |
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///./jobbi.db` |
| `ACCESS_TOKEN_EXPIRE_DAYS` | JWT token lifetime | `7` |
| `SENTRY_DSN` | Sentry error tracking | `https://...@sentry.io/...` |
| `CORS_ORIGINS` | Allowed frontend origins | `http://localhost:5173` |
| `VITE_API_URL` | Frontend → backend URL | `http://localhost:8000` |

---

## 3. Impact and Risk Analysis

**System Dependencies:**
- This is the foundation — no existing system dependencies. All future features depend on the auth and user models established here.

**Potential Risks & Mitigations:**

| Risk | Impact | Mitigation |
|---|---|---|
| JWT secret key leakage | Full account compromise | Store in `.env`, never commit. Add `.env` to `.gitignore` from day one. |
| Password stored insecurely | Account compromise | Use bcrypt with sufficient work factor (12 rounds). Never log or return password hashes. |
| Reset token brute-force | Unauthorized password reset | Use crypto-random tokens (32+ bytes), hash before storing, enforce 1-hour expiry and single-use. |
| SQLite concurrent writes | Data corruption in future multi-user scenario | Using SQLAlchemy ORM keeps migration to PostgreSQL trivial. Acceptable risk for V1 single-user. |
| JWT in local storage vulnerable to XSS | Token theft | Mitigate with Content Security Policy headers and input sanitization. Acceptable trade-off for V1 simplicity vs. httpOnly cookies. |

---

## 4. Testing Strategy

**Backend (pytest):**
- Unit tests for `auth_service.py` (password hashing, token generation, user creation)
- Integration tests for all API endpoints (register, login, forgot/reset password, profile CRUD, change password)
- Test error cases: duplicate email, wrong password, expired reset token, missing auth header

**Frontend (Vitest + Testing Library):**
- Component tests for login/register/settings forms (validation, submission, error display)
- Auth store tests (login/logout actions, token persistence)
- Protected route tests (redirect to login when not authenticated)