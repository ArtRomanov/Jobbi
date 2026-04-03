# Functional Specification: User Account Essentials

- **Roadmap Item:** User Account Essentials (Phase 1 — Foundation & Application Tracking)
- **Status:** Completed
- **Author:** Poe (AI Product Analyst)

---

## 1. Overview and Rationale (The "Why")

Jobbi is a personal job search assistant, and every feature depends on a user identity. Without accounts, there's no way to persist data, secure access, or personalize the experience.

**Problem:** The user needs a secure, personal entry point to Jobbi where their job applications, CVs, and metrics are tied to their identity and protected from unauthorized access.

**Desired outcome:** A frictionless sign-up and login experience that collects essential job search context upfront, so the app is immediately personalized from the first session. The user can manage their profile and preferences at any time, and recover access if they forget their password.

**Success criteria:**
- A new user can sign up, land on the dashboard, and see their name within 60 seconds.
- The user never needs to re-enter their credentials unless they explicitly log out or the token expires.
- Password recovery works end-to-end without manual database intervention.

---

## 2. Functional Requirements (The "What")

### 2.1 Sign-Up

- **As a** new user, **I want to** create an account with my details and job search preferences, **so that** Jobbi is personalized from the start.
  - **Acceptance Criteria:**
    - [x] The sign-up form collects: full name, email address, password, desired role/title, desired location/remote preference, and salary expectations.
    - [x] Email must be a valid email format. Duplicate emails are rejected with the message: "An account with this email already exists."
    - [x] Password must be at least 8 characters. If shorter, show: "Password must be at least 8 characters."
    - [x] Desired role/title is a free-text field (e.g., "Senior Frontend Engineer").
    - [x] Desired location is a free-text field with a remote preference toggle (On-site / Remote / Hybrid).
    - [x] Salary expectations is an optional field with a numeric range (min–max) and currency selector.
    - [x] On successful sign-up, the user is automatically logged in and redirected to the main dashboard.
    - [x] All preferences fields (role, location, salary) are optional — the user can skip them during sign-up and fill them in later via profile settings.

### 2.2 Login

- **As a** returning user, **I want to** log in with my email and password, **so that** I can access my job search data.
  - **Acceptance Criteria:**
    - [x] The login form collects: email address and password.
    - [x] On successful login, the user is redirected to the main dashboard.
    - [x] On failed login (wrong email or wrong password), a generic error message is shown: "Invalid email or password."
    - [x] The user remains logged in across browser sessions (JWT persisted in local storage) until they explicitly log out or the token expires.
    - [x] There is a "Forgot Password?" link on the login page.

### 2.3 Forgot Password

- **As a** user who forgot their password, **I want to** reset it via email, **so that** I can regain access to my account.
  - **Acceptance Criteria:**
    - [x] Clicking "Forgot Password?" navigates to a page with an email input field.
    - [x] After submitting an email, the user sees a confirmation message: "If an account with that email exists, we've sent a password reset link." (Generic — doesn't confirm whether the email is registered.)
    - [x] If the email exists, a reset link is sent to that address. The link expires after 1 hour.
    - [x] Clicking the reset link opens a "Set New Password" page with a password field and a confirmation field.
    - [x] After successfully resetting, the user is redirected to the login page with a success message: "Password reset successfully. Please log in."
    - [x] If the link is expired or already used, the user sees: "This reset link has expired. Please request a new one."

### 2.4 Profile Management

- **As a** logged-in user, **I want to** view and edit my name and job search preferences, **so that** I can keep my profile current as my search evolves.
  - **Acceptance Criteria:**
    - [x] A "Profile" or "Settings" page is accessible from the main navigation.
    - [x] The user can view and edit: full name, desired role/title, desired location/remote preference, and salary expectations.
    - [x] Email is displayed but not editable on this page. [NEEDS CLARIFICATION: Should there be a separate "Change Email" flow, or is email fixed after registration for V1?]
    - [x] Changes are saved with a "Save" button. On success, show a confirmation message: "Profile updated."
    - [x] Validation rules match the sign-up form (e.g., name is required).

### 2.5 Change Password

- **As a** logged-in user, **I want to** change my password from within the app, **so that** I can update my security credentials without going through the forgot password flow.
  - **Acceptance Criteria:**
    - [x] A "Change Password" section is accessible from the Profile/Settings page.
    - [x] The user must enter their current password and a new password (8+ characters).
    - [x] If the current password is wrong, show: "Current password is incorrect."
    - [x] On success, show: "Password changed successfully."

### 2.6 Logout

- **As a** logged-in user, **I want to** log out, **so that** my session is ended securely.
  - **Acceptance Criteria:**
    - [x] A "Log Out" option is accessible from the main navigation or profile menu.
    - [x] On logout, the JWT token is cleared and the user is redirected to the login page.

---

## 3. Scope and Boundaries

### In-Scope

- Sign-up form with name, email, password, and job search preferences (role, location, salary)
- Login with email and password
- Persistent sessions via JWT (local storage)
- Forgot password flow with email reset link
- Profile editing (name and preferences)
- Change password (from within the app)
- Logout

### Out-of-Scope

- **Application Tracker** (separate roadmap item — Phase 1)
- **CV Constructor** (Phase 2)
- **Claude Chat Integration** (Phase 2)
- **Metrics Dashboard** (Phase 3)
- **Telegram Bot Integration** (Phase 4)
- **HeadHunter Integration** (Phase 4)
- **LinkedIn Integration** (Phase 4)
- OAuth / social login (Google, GitHub)
- Email verification on sign-up
- Account deletion
- Multi-factor authentication
- Avatar / profile picture upload