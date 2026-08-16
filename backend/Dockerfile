# ============================================
# Stage 1: Builder — install dependencies
# ============================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install system deps needed for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================
# Stage 2: Runtime — lean production image
# ============================================
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install only runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Create non-root user for security
RUN addgroup --system appuser && adduser --system --ingroup appuser appuser
USER appuser

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production: gunicorn with uvicorn workers
# Override with CMD in docker-compose for dev
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
