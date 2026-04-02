# Tasks: User Account Essentials

---

- [x] **Slice 1: Project skeleton with running backend + frontend**
  - [x] Initialize the backend: Python project with `pyproject.toml`, FastAPI app with a health-check endpoint (`GET /api/v1/health` → `{ status: "ok" }`), structlog setup, Sentry init stub. **[Agent: python-backend]**
  - [x] Initialize the frontend: React + Vite + TypeScript project with FSD directory structure (`app/`, `pages/`, `features/`, `entities/`, `shared/`), a placeholder home page. **[Agent: typescript-frontend]**
  - [x] Create `Dockerfile` for backend (multi-stage, Python 3.11+) and `Dockerfile` for frontend (multi-stage, Node 20+). **[Agent: devops-infra]**
  - [x] Create `docker-compose.yml` with backend and frontend services, `.env.example` with all env vars, and `.gitignore` (include `.env`, `__pycache__`, `node_modules`, `*.db`). **[Agent: devops-infra]**
  - [x] Verify: Run `docker compose up`, confirm backend health endpoint returns 200 and frontend loads in browser at `localhost:5173`. **[Agent: qa-tester]**

---

- [x] **Slice 2: User can register via API**
  - [x] Set up SQLAlchemy async engine, session factory, and Alembic configuration. Create initial migration with `users` table (all columns per tech spec). **[Agent: database-expert]**
  - [x] Create Pydantic schemas: `RegisterRequest` (email, password, full_name, preferences), `AuthResponse` (access_token, token_type, user), `UserRead`. **[Agent: python-backend]**
  - [x] Implement `core/security.py`: bcrypt password hashing, JWT token creation/verification. **[Agent: python-backend]**
  - [x] Implement `core/config.py`: Pydantic Settings loading SECRET_KEY, DATABASE_URL, ACCESS_TOKEN_EXPIRE_DAYS from env. **[Agent: python-backend]**
  - [x] Implement `core/deps.py`: `get_db` session dependency, `get_current_user` dependency (JWT → User). **[Agent: python-backend]**
  - [x] Implement `services/auth_service.py`: `create_user()` (hash password, insert, return user), `authenticate_user()` (verify email + password). **[Agent: python-backend]**
  - [x] Implement `POST /api/v1/auth/register` endpoint: validate input, check duplicate email (409), create user, return JWT + user. **[Agent: python-backend]**
  - [x] Verify: `curl -X POST localhost:8000/api/v1/auth/register` with valid payload returns 201 + token. Duplicate email returns 409. Invalid payload returns 422. **[Agent: qa-tester]**

---

- [x] **Slice 3: User can register and log in through the UI**
  - [x] Implement `POST /api/v1/auth/login` endpoint: verify credentials, return JWT + user, or 401 on failure. **[Agent: python-backend]**
  - [x] Implement CORS configuration in `main.py` (allow frontend origin). **[Agent: python-backend]**
  - [x] Create `shared/api/` fetch wrapper: base URL from env, auto-attach JWT header, JSON helper methods. **[Agent: typescript-frontend]**
  - [x] Create `shared/ui/` base components: FormInput, Button, Toast notification. **[Agent: typescript-frontend]**
  - [x] Create `features/auth/` Zustand store: `token`, `isAuthenticated`, `login()`, `logout()`, persist token to localStorage. **[Agent: typescript-frontend]**
  - [x] Create `pages/register/` page: sign-up form (React Hook Form + Zod), all fields per spec (name, email, password, preferences with optional fields). On success → store token → redirect to dashboard placeholder. **[Agent: typescript-frontend]**
  - [x] Create `pages/login/` page: email + password form (React Hook Form + Zod). On success → store token → redirect to dashboard. On error → show "Invalid email or password." **[Agent: typescript-frontend]**
  - [x] Create `app/router/`: routes for `/login`, `/register`, `/dashboard` (placeholder), `ProtectedRoute` wrapper (redirect to `/login` if not authed). **[Agent: typescript-frontend]**
  - [x] Code review: Review all new frontend code for React best practices, FSD compliance, Zustand patterns, and TypeScript quality. **[Agent: react-code-reviewer]**
  - [x] Verify: Open browser → register → auto-redirected to dashboard. Close browser → reopen → still logged in. Log out → go to `/login` → log in → dashboard. Wrong password → error shown. **[Agent: qa-tester]**

---

- [ ] **Slice 4: User can view and edit their profile**
  - [ ] Implement `GET /api/v1/users/me` endpoint: return current user data from JWT. **[Agent: python-backend]**
  - [ ] Implement `PATCH /api/v1/users/me` endpoint: update name and preferences (not email). Return updated user. **[Agent: python-backend]**
  - [ ] Create `entities/user/` slice: User type definitions, `getMe()` API call, user query hook. **[Agent: typescript-frontend]**
  - [ ] Create `pages/settings/` page: profile form pre-filled with current user data (React Hook Form + Zod). Save button → `PATCH /users/me` → success toast "Profile updated." Email displayed read-only. **[Agent: typescript-frontend]**
  - [ ] Add navigation: settings link in app header/sidebar, accessible when logged in. **[Agent: typescript-frontend]**
  - [ ] Code review: Review settings page, user entity slice, and navigation for FSD compliance and React patterns. **[Agent: react-code-reviewer]**
  - [ ] Verify: Log in → navigate to settings → see pre-filled profile → edit name → save → refresh → changes persisted. **[Agent: qa-tester]**

---

- [ ] **Slice 5: User can change their password**
  - [ ] Implement `POST /api/v1/users/me/change-password` endpoint: verify current password, update to new password, or 400 if wrong. **[Agent: python-backend]**
  - [ ] Add "Change Password" section to `pages/settings/`: form with current password, new password (8+ chars). On success → toast "Password changed successfully." On error → "Current password is incorrect." **[Agent: typescript-frontend]**
  - [ ] Code review: Review change password form integration for patterns and security. **[Agent: react-code-reviewer]**
  - [ ] Verify: Log in → settings → change password with correct current → success. Try logging in with old password → fails. Log in with new password → succeeds. Try wrong current password → error shown. **[Agent: qa-tester]**

---

- [ ] **Slice 6: User can reset a forgotten password**
  - [ ] Create `password_reset_tokens` table via Alembic migration (all columns per tech spec). **[Agent: database-expert]**
  - [ ] Implement `POST /api/v1/auth/forgot-password` endpoint: generate crypto-random token, hash with SHA-256, store in DB, log reset link to console. Always return 200 with generic message. **[Agent: python-backend]**
  - [ ] Implement `POST /api/v1/auth/reset-password` endpoint: hash submitted token, look up in DB, check expiry and used_at, update password, mark token used. 400 if expired/used. **[Agent: python-backend]**
  - [ ] Create `pages/forgot-password/` page: email input form. On submit → show "If an account with that email exists, we've sent a password reset link." **[Agent: typescript-frontend]**
  - [ ] Create `pages/reset-password/` page: reads `token` from URL query param. New password + confirm password form. On success → redirect to `/login` with success message. On error (expired) → show "This reset link has expired." **[Agent: typescript-frontend]**
  - [ ] Add "Forgot Password?" link to the login page. **[Agent: typescript-frontend]**
  - [ ] Code review: Review forgot/reset password pages for form handling, error states, and FSD compliance. **[Agent: react-code-reviewer]**
  - [ ] Verify: Go to forgot password → submit email → check backend console for reset link → open link → set new password → redirect to login → log in with new password. Also test: expired token → error shown. Reuse same token → error shown. **[Agent: qa-tester]**

---

- [ ] **Slice 7: User can log out**
  - [ ] Implement `POST /api/v1/auth/logout` endpoint: returns 200 (placeholder for future server-side invalidation). **[Agent: python-backend]**
  - [ ] Add "Log Out" button to navigation/header. On click → call logout endpoint → clear token from Zustand + localStorage → redirect to `/login`. **[Agent: typescript-frontend]**
  - [ ] Code review: Review logout integration and navigation updates. **[Agent: react-code-reviewer]**
  - [ ] Verify: Log in → click logout → redirected to login → visiting `/dashboard` redirects to login → JWT cleared from localStorage. **[Agent: qa-tester]**

---

- [ ] **Slice 8: Backend test suite**
  - [ ] Set up pytest with async fixtures, test database (in-memory SQLite), test client. **[Agent: python-backend]**
  - [ ] Unit tests for `security.py`: password hashing roundtrip, JWT creation/decode, token expiry. **[Agent: python-backend]**
  - [ ] Integration tests for auth endpoints: register (success, duplicate, validation), login (success, wrong creds), forgot password, reset password (success, expired, reused). **[Agent: python-backend]**
  - [ ] Integration tests for user endpoints: get profile, update profile, change password (success, wrong current password). **[Agent: python-backend]**
  - [ ] Verify: `pytest` runs all tests — 100% pass rate. **[Agent: qa-tester]**

---

- [ ] **Slice 9: Frontend test suite**
  - [ ] Set up Vitest with Happy-DOM, Testing Library, MSW v2 handlers for all API endpoints. **[Agent: typescript-frontend]**
  - [ ] Component tests: login form (validation, submit, error display), register form (validation, optional fields, submit). **[Agent: typescript-frontend]**
  - [ ] Component tests: settings page (pre-filled data, save, change password). **[Agent: typescript-frontend]**
  - [ ] Auth store tests: login stores token, logout clears token, isAuthenticated reflects state. **[Agent: typescript-frontend]**
  - [ ] Protected route test: unauthenticated user redirected to `/login`. **[Agent: typescript-frontend]**
  - [ ] Code review: Review all test code for testing best practices, query selection philosophy, and proper async patterns. **[Agent: react-code-reviewer]**
  - [ ] Verify: `npx vitest run` — 100% pass rate. **[Agent: qa-tester]**