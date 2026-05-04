# System Architecture Overview: Jobbi

---

## 1. Application & Technology Stack

- **Frontend Framework:** React + Vite (TypeScript)
- **Backend Framework:** Python + FastAPI
- **ORM:** SQLAlchemy (standard patterns only — no SQLite-specific features, to keep PostgreSQL migration trivial)
- **API Style:** RESTful JSON API
- **Language Standards:** TypeScript (frontend), Python 3.11+ (backend)

---

## 2. Data & Persistence

- **Primary Database:** SQLite (via SQLAlchemy ORM)
- **Migration Tool:** Alembic (SQLAlchemy's migration companion)
- **Caching:** None for V1 (single-user app, direct DB queries are sufficient)
- **File Storage:** Local filesystem (for CV document storage)

> **Note:** SQLite chosen for simplicity. The ORM abstraction ensures a straightforward migration path to PostgreSQL if needed. All database interactions must use standard SQLAlchemy patterns — avoid SQLite-specific features.

---

## 3. Infrastructure & Deployment

- **Deployment Target:** Local only (V1)
- **Local Development:** Docker Compose (frontend + backend containers)
- **Containerization:** Docker (one container per service)
- **Future Deployment:** TBD — Docker-based setup makes migration to VPS or cloud straightforward

---

## 4. External Services & APIs

- **Authentication:** Simple email + password (hashed with bcrypt, JWT tokens for session management)
- **AI Integration:** Groq API (direct HTTPS calls via official Python SDK)
- **API Key Management:** Environment variables (`.env` file, not committed to source control)

---

## 5. Observability & Monitoring

- **Logging:** Structured JSON logging (Python `structlog` or `python-json-logger`)
- **Error Tracking:** Sentry (captures unhandled exceptions and error context)
- **Metrics:** None for V1 (application-level metrics dashboard covers user-facing stats)