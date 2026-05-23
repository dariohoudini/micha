#!/bin/sh
#
# Container entrypoint. Dispatches the chosen role.
#
# Roles (passed as $1):
#   web     — gunicorn WSGI for the REST API (default)
#   worker  — celery worker (queues: high, default, low)
#   beat    — celery beat scheduler (singleton in prod via Redis lock)
#   daphne  — daphne ASGI for WebSocket + channels
#   migrate — run migrations and exit (init container in k8s, or
#             docker-compose one-shot)
#   shell   — drop into a python manage.py shell (interactive)
#
# Env vars consumed:
#   DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
#     used by wait-for-postgres
#   REDIS_URL (optional) — checked by wait-for-redis
#   MIGRATE_ON_START   = "1" | "0"  (default 0)
#     when "1", run migrations before starting the role. Useful in
#     dev / staging. In prod, prefer a dedicated migrate init container
#     so multiple replicas don't race the migrations.
#   COLLECT_STATIC_ON_START = "1" | "0" (default 1 for web role)
#     collects static files into STATIC_ROOT.
#   GUNICORN_WORKERS, GUNICORN_THREADS — see config/gunicorn.conf.py

set -eu

ROLE="${1:-web}"
log() { printf '[entrypoint] %s\n' "$*" >&2; }

wait_for_postgres() {
    if [ -z "${DB_HOST:-}" ]; then
        log "DB_HOST not set, skipping postgres wait"
        return 0
    fi
    log "Waiting for Postgres at ${DB_HOST}:${DB_PORT:-5432}..."
    for i in $(seq 1 60); do
        if pg_isready -h "${DB_HOST}" -p "${DB_PORT:-5432}" -U "${DB_USER:-postgres}" >/dev/null 2>&1; then
            log "Postgres ready"
            return 0
        fi
        sleep 1
    done
    log "Postgres did not become ready after 60s — failing"
    return 1
}

wait_for_redis() {
    if [ -z "${REDIS_URL:-}" ]; then
        log "REDIS_URL not set, skipping redis wait"
        return 0
    fi
    # Extract host:port from REDIS_URL (redis://host:port/db)
    REDIS_HOST=$(printf '%s' "$REDIS_URL" | sed -E 's|redis://||; s|:.*||')
    REDIS_PORT=$(printf '%s' "$REDIS_URL" | sed -E 's|.*:([0-9]+)(/.*)?$|\1|')
    log "Waiting for Redis at ${REDIS_HOST}:${REDIS_PORT}..."
    for i in $(seq 1 30); do
        # Use python's socket since we don't have redis-cli installed
        if python -c "import socket; s=socket.socket(); s.connect(('${REDIS_HOST}', ${REDIS_PORT})); s.close()" >/dev/null 2>&1; then
            log "Redis ready"
            return 0
        fi
        sleep 1
    done
    log "Redis did not become ready after 30s — failing"
    return 1
}

run_migrations_if_requested() {
    if [ "${MIGRATE_ON_START:-0}" = "1" ]; then
        log "MIGRATE_ON_START=1 → running migrations"
        python manage.py migrate --noinput
    fi
}

collect_static_if_requested() {
    if [ "${COLLECT_STATIC_ON_START:-1}" = "1" ]; then
        log "Collecting static files"
        python manage.py collectstatic --noinput --clear 2>/dev/null || \
            log "collectstatic failed (non-fatal in dev)"
    fi
}

# ── Dispatch ──────────────────────────────────────────────────────
case "$ROLE" in
    web)
        wait_for_postgres
        wait_for_redis
        run_migrations_if_requested
        collect_static_if_requested
        log "Starting gunicorn (web)"
        exec gunicorn config.wsgi:application -c config/gunicorn.conf.py
        ;;

    worker)
        wait_for_postgres
        wait_for_redis
        # Multiple queues, one worker process per container in
        # production (orchestrator scales horizontally).
        # ``--without-mingle --without-gossip --without-heartbeat``
        # cuts startup chatter for cleaner logs.
        log "Starting celery worker"
        exec celery -A config worker \
            -l info \
            -Q "${CELERY_QUEUES:-high,default,low}" \
            -c "${CELERY_CONCURRENCY:-4}" \
            --without-mingle \
            --without-gossip
        ;;

    beat)
        wait_for_postgres
        wait_for_redis
        # CRITICAL: beat must run as a SINGLETON across the cluster.
        # Without a lock, multiple beat instances duplicate every
        # scheduled job. We rely on apps.core.task_locks.singleton_task
        # at the task level for defence-in-depth, but the
        # orchestrator (k8s deployment with replicas: 1, or compose
        # without scale) is the primary guarantee.
        log "Starting celery beat (MUST be singleton)"
        exec celery -A config beat \
            -l info \
            --pidfile=/tmp/celerybeat.pid
        ;;

    daphne)
        wait_for_postgres
        wait_for_redis
        log "Starting daphne (ASGI websocket)"
        exec daphne -b 0.0.0.0 -p "${DAPHNE_PORT:-8001}" config.asgi:application
        ;;

    migrate)
        wait_for_postgres
        log "Running migrations (one-shot)"
        exec python manage.py migrate --noinput
        ;;

    shell)
        wait_for_postgres
        exec python manage.py shell
        ;;

    *)
        log "Unknown role: $ROLE"
        log "Usage: entrypoint.sh {web|worker|beat|daphne|migrate|shell}"
        exit 1
        ;;
esac
