#!/bin/bash
# MICHA Production Deploy Script
# FIX: Checks migrations before deploy, no partial deploys

set -euo pipefail

echo "[$(date)] Starting MICHA deployment..."

# 1. Check for pending migrations (never deploy with unapplied migrations)
echo "Checking migrations..."
python manage.py migrate --check 2>/dev/null && echo "✓ No pending migrations" || {
    echo "ERROR: Pending migrations detected. Run: python manage.py migrate"
    exit 1
}

# 2. Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput -v 0
echo "✓ Static files collected"

# 3. Run migrations (only if check passed)
python manage.py migrate --run-syncdb
echo "✓ Migrations applied"

# 4. Restart services (supervisor)
if command -v supervisorctl > /dev/null 2>&1; then
    supervisorctl restart micha:*
    echo "✓ Services restarted via supervisor"
else
    # Docker compose
    docker-compose up -d --build
    echo "✓ Docker services restarted"
fi

# 5. Health check
sleep 5
if curl -sf http://localhost:8000/health/ | grep -q '"status":"ok"'; then
    echo "✓ Health check passed"
else
    echo "ERROR: Health check failed after deploy!"
    exit 1
fi

echo "[$(date)] Deploy complete!"
