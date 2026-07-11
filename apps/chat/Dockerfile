# Build from the repo root: docker build -f apps/chat/Dockerfile -t nextwork-chat-service .
# (build context must be the repo root, not apps/chat/, since this also needs libs/shared/)
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# curl is for the HEALTHCHECK below, not the app itself
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install deps first so this layer stays cached across source-only changes
COPY apps/chat/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App source - only this service's own files plus the shared lib (see
# apps/chat/query_routes.py and apps/chat/session_routes.py's dependency
# chains), so this image doesn't carry auth-service-only code/dependencies
# (bcrypt, resend, ...).
COPY libs/shared/ ./libs/shared/
COPY apps/chat/*.py ./apps/chat/

# Don't run the app as root inside the container
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
# Worker count is tunable via UVICORN_WORKERS (defaults to 4) rather than
# hardcoded, since the right value depends on the container's CPU allocation.
# `exec` (not plain shell form) so uvicorn replaces the shell as PID 1 and
# still receives SIGTERM directly for graceful shutdown.
CMD ["sh", "-c", "exec uvicorn apps.chat.app:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-4}"]
