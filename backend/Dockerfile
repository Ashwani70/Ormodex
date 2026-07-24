# Ormodex ERP — FastAPI backend, production image.
#
# Multi-stage: build wheels in a full image, run in a slim one. Runs Gunicorn
# as the process manager (auto-restarts crashed workers) with Uvicorn's ASGI
# worker class underneath — the standard production combo for FastAPI, since
# `uvicorn` alone has no worker-supervision/auto-restart of its own.

FROM python:3.12-slim AS builder

WORKDIR /app

# System deps needed to build wheels for asyncpg/cryptography/etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


FROM python:3.12-slim AS runtime

# Runtime-only system deps (libpq for asyncpg's C extension, curl for the
# container healthcheck below).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local
COPY --chown=appuser:appuser . .

# Uploads dir must exist and be writable even before a volume is mounted over
# it (local dev / first boot) — see core/storage.py LOCAL_STORAGE_DIR.
RUN mkdir -p /app/uploads && chown -R appuser:appuser /app/uploads

USER appuser
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# Liveness probe used by both `docker run --health-cmd` consumers and as
# documentation for platform-level healthchecks (Railway reads PORT itself).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Gunicorn supervises N Uvicorn workers: if a worker dies (unhandled crash,
# memory leak), Gunicorn restarts it without the whole container going down.
# --workers is overridable via WEB_CONCURRENCY; 2 is a safe default for a
# small Railway instance (CPU-bound work here is minimal — most latency is
# I/O-bound DB round-trips, so more workers than cores is fine).
CMD gunicorn server:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers ${WEB_CONCURRENCY:-2} \
    --bind 0.0.0.0:${PORT:-8000} \
    --timeout 60 \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile - \
    --log-level info
