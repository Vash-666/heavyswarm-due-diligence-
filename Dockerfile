# =============================================================================
# HeavySwarm Investment Due Diligence Engine - Dockerfile
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Base Image
# -----------------------------------------------------------------------------
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# -----------------------------------------------------------------------------
# Stage 2: Dependencies
# -----------------------------------------------------------------------------
FROM base as dependencies

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies
RUN pip install --upgrade pip && \
    pip install -e ".[dev]"

# -----------------------------------------------------------------------------
# Stage 3: Development
# -----------------------------------------------------------------------------
FROM dependencies as development

# Copy source code
COPY . .

# Install in editable mode with dev dependencies
RUN pip install -e ".[dev]"

# Expose port
EXPOSE 8000

# Default command for development
CMD ["uvicorn", "heavyswarm.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# -----------------------------------------------------------------------------
# Stage 4: Production
# -----------------------------------------------------------------------------
FROM base as production

# Create non-root user
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Copy installed packages from dependencies stage
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=appuser:appgroup src/ ./src/
COPY --chown=appuser:appgroup config/ ./config/
COPY --chown=appuser:appgroup prompts/ ./prompts/
COPY --chown=appuser:appgroup migrations/ ./migrations/
COPY --chown=appuser:appgroup alembic.ini ./
COPY --chown=appuser:appgroup pyproject.toml ./

# Install package (not editable)
RUN pip install .

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command for production
CMD ["uvicorn", "heavyswarm.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
