# Build from the repo root: docker build -f apps/auth/Dockerfile -t nextwork-auth-service .
# (build context must be the repo root, not apps/auth/, since this also needs libs/shared/)
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# curl is for the HEALTHCHECK below, not the app itself
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install deps first so this layer stays cached across source-only changes
COPY apps/auth/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App source - only this service's own files plus the shared lib (see
# apps/auth/routes.py's dependency chain), so this image doesn't carry
# chat-service-only code/dependencies (ollama, chromadb, pandas, ...).
COPY libs/shared/ ./libs/shared/
COPY apps/auth/*.py ./apps/auth/

# Don't run the app as root inside the container
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1
# Worker count is tunable via UVICORN_WORKERS (defaults to 4) rather than
# hardcoded, since the right value depends on the container's CPU allocation.
# `exec` (not plain shell form) so uvicorn replaces the shell as PID 1 and
# still receives SIGTERM directly for graceful shutdown.
CMD ["sh", "-c", "exec uvicorn apps.auth.app:app --host 0.0.0.0 --port 8001 --workers ${UVICORN_WORKERS:-4}"]
