#!/bin/bash
# Start all MICHA services for local development
# Usage: bash scripts/run_dev.sh

set -e

echo "=== MICHA Dev Environment ==="

# Check Redis
if ! redis-cli ping > /dev/null 2>&1; then
    echo "Starting Redis..."
    brew services start redis 2>/dev/null || redis-server --daemonize yes
fi
echo "✓ Redis running"

# Run migrations
echo "Running migrations..."
python manage.py migrate --run-syncdb 2>/dev/null || python manage.py migrate
echo "✓ Migrations applied"

# Collect static files
python manage.py collectstatic --noinput -v 0
echo "✓ Static files collected"

# Start services in background
echo "Starting Celery worker..."
celery -A config worker -l info -c 2 -Q high,default,low > /tmp/celery.log 2>&1 &
CELERY_PID=$!
echo "✓ Celery worker PID: $CELERY_PID"

echo "Starting Celery beat..."
celery -A config beat -l info > /tmp/celery_beat.log 2>&1 &
BEAT_PID=$!
echo "✓ Celery beat PID: $BEAT_PID"

echo ""
echo "=== Starting Django development server ==="
echo "API:    http://127.0.0.1:8000"
echo "Admin:  http://127.0.0.1:8000/admin/"
echo "Health: http://127.0.0.1:8000/health/"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Trap Ctrl+C to clean up background processes
cleanup() {
    echo "Stopping all services..."
    kill $CELERY_PID $BEAT_PID 2>/dev/null || true
    exit 0
}
trap cleanup INT TERM

python manage.py runserver
