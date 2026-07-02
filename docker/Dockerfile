# MICHA backend container.
#
# One image, multiple roles: same code runs as the gunicorn web
# server, celery worker, celery beat, or daphne websocket process.
# The CMD picks the role; docker-compose.yml + production orchestrator
# (k8s / ECS) override per service.
#
# Multi-stage build:
#   • ``builder`` stage installs Python deps into a wheel cache
#   • ``runtime`` stage copies wheels + source, drops build tooling
#
# Result: ~280MB image (vs ~700MB single-stage) and faster CI rebuilds
# because the deps layer is cached separately from the source layer.

# ╭─────────────────────────────────────────────────────────────────╮
# │  Builder stage                                                  │
# ╰─────────────────────────────────────────────────────────────────╯
FROM python:3.13-slim AS builder

# System deps needed to COMPILE Python packages with C extensions
# (psycopg2, cryptography, Pillow). NOT in the runtime image — runtime
# uses pre-built wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libjpeg-dev \
    libpng-dev \
    zlib1g-dev \
    libwebp-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy ONLY requirements.txt first — Docker caches this layer until
# requirements.txt changes. App source changes don't bust the deps
# cache. CI rebuilds in ~10s instead of 3min when only code changed.
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.txt


# ╭─────────────────────────────────────────────────────────────────╮
# │  Runtime stage                                                  │
# ╰─────────────────────────────────────────────────────────────────╯
FROM python:3.13-slim AS runtime

# Runtime system deps. Image-vision libs need their shared libraries
# (libjpeg, libwebp, libpng) at runtime even though we built wheels.
# Postgres client used by entrypoint.sh's `pg_isready` health probe.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libjpeg62-turbo \
    libpng16-16 \
    libwebp7 \
    postgresql-client \
    curl \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Non-root user. Running Python web processes as root is unnecessary
# privilege; if a process is compromised, the blast radius is bounded
# to /app and the user's home.
RUN groupadd -r micha && useradd --no-log-init -r -g micha -d /app micha

WORKDIR /app

# Install Python deps from the wheel cache built in the previous
# stage. No compilers in this image; the wheels are pre-built.
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl && \
    rm -rf /wheels

# Copy source. Order matters: copy AFTER deps so a code-only change
# doesn't rebuild the deps layer.
COPY --chown=micha:micha . /app/

# Entrypoint handles:
#   • waiting for Postgres/Redis to be ready
#   • optionally running migrations (only when MIGRATE_ON_START=1)
#   • dispatching to the requested process (web / worker / beat / daphne)
RUN chmod +x /app/docker/entrypoint.sh

# Drop to non-root before final stage.
USER micha

# Default port for the gunicorn role. docker-compose / orchestrator
# overrides per service.
EXPOSE 8000

# tini reaps zombie processes — important for celery workers which
# spawn subprocesses. Without tini, a crashed worker leaves zombie
# children that exhaust the PID table over weeks.
ENTRYPOINT ["/usr/bin/tini", "--", "/app/docker/entrypoint.sh"]

# Readiness probe (Gap-Coverage CH9D): the orchestrator must distinguish
# a started-but-not-ready container from a healthy one. /health/ready
# checks DB + cache; /health/ (liveness alias) only proves the process
# is up. Only meaningful for the web/daphne roles — worker/beat
# containers get their healthcheck overridden (or disabled) per-service
# in compose / the orchestrator, since they serve no HTTP port.
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:8000/health/ready || exit 1

# Default role: gunicorn web. Override with one of:
#   "worker" | "beat" | "daphne" | "migrate" | "shell"
CMD ["web"]
