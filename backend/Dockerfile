# ---- Build stage ----
FROM python:3.11-slim AS builder

WORKDIR /build

# Copy dependency metadata first for layer caching
COPY pyproject.toml .

# Install build dependencies and project
RUN pip install --no-cache-dir build hatchling

# Copy source code
COPY app/ app/

# Build wheel
RUN python -m build --wheel --outdir /build/dist

# ---- Production stage ----
FROM python:3.11-slim AS production

WORKDIR /app

# Install the built wheel
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Copy application source (needed at runtime since uvicorn imports app.main)
COPY app/ app/

# Create non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

# Create data directory for SQLite volume mount
RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8003

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
