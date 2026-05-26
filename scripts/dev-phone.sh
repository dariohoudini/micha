#!/usr/bin/env bash
# scripts/dev-phone.sh
# ─────────────────────
# Start backend + frontend bound to all interfaces so your phone can
# reach the dev server over WiFi. Auto-detects LAN IP and prints the
# URL to type on your phone.
#
# Usage:
#   ./scripts/dev-phone.sh
#
# Both servers run in the foreground inside one tmux-less wrapper —
# the script uses ``wait`` so a single Ctrl+C tears down both.

set -e

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

# ── LAN IP detection ─────────────────────────────────────────────
detect_ip() {
  # macOS prefers en0 (WiFi). Linux varies. We pick the first
  # non-loopback IPv4 that's NOT a Docker bridge (172.17.x).
  if command -v ipconfig >/dev/null 2>&1; then
    IP=$(ipconfig getifaddr en0 2>/dev/null || true)
    [ -n "$IP" ] && { echo "$IP"; return; }
    IP=$(ipconfig getifaddr en1 2>/dev/null || true)
    [ -n "$IP" ] && { echo "$IP"; return; }
  fi
  # ifconfig fallback (BSD + Linux).
  ifconfig 2>/dev/null \
    | awk '/inet / && !/127.0.0.1/ && !/172.17/ {print $2; exit}'
}

LAN_IP=$(detect_ip)
if [ -z "$LAN_IP" ]; then
  echo "❌ Could not detect your LAN IP. Are you on WiFi?"
  echo "   Find it manually: macOS → System Preferences → Network"
  exit 1
fi

# ── Print banner ─────────────────────────────────────────────────
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
RESET='\033[0m'

cat <<EOF

${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}
${BOLD}MICHA — Phone Dev Mode${RESET}
${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}

Your dev machine LAN IP: ${BOLD}${GREEN}${LAN_IP}${RESET}

On your phone (same WiFi network), open:

    ${BOLD}${GREEN}http://${LAN_IP}:5173/${RESET}

Bookmark it. Hot-reload works.

${YELLOW}⚠  Both devices must be on the same WiFi network.
   If your home WiFi has "client isolation" enabled (common on
   guest networks), this won't work — switch to the main SSID.${RESET}

${BOLD}Starting backend on  ${LAN_IP}:8000${RESET}
${BOLD}Starting frontend on ${LAN_IP}:5173${RESET}

Press Ctrl+C to stop both.

EOF

# ── Start backend ────────────────────────────────────────────────
# Force SQLite for dev. The project .env file declares Postgres
# credentials for prod-like runs; config/settings.py:_read_env() uses
# os.environ.setdefault() which respects exported values. By
# EXPORTING empty DB_NAME here, settings.py's
# ``if os.environ.get('DB_NAME')`` check returns falsy and the
# SQLite fallback branch activates.
export DB_NAME=""
export DB_USER=""
export DB_PASSWORD=""
export DB_HOST=""
export DB_PORT=""

export DJANGO_SETTINGS_MODULE=config.settings
export ALLOWED_HOSTS="localhost,127.0.0.1,0.0.0.0,${LAN_IP}"
export MIGRATION_UNSAFE_ALLOWED=1
export CORS_ALLOWED_ORIGINS="http://localhost:5173,http://127.0.0.1:5173,http://${LAN_IP}:5173"
export DEBUG=True

if [ ! -d "venv" ]; then
  echo "❌ ./venv not found. Run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

# Apply migrations on first run so SQLite has the right schema.
if [ ! -f "db.sqlite3" ]; then
  echo "📦 First-time DB setup (applying migrations)…"
  ./venv/bin/python manage.py migrate --noinput \
    > /tmp/micha-phone-dev-migrate.log 2>&1 || {
    echo "❌ Migration failed. See /tmp/micha-phone-dev-migrate.log"
    exit 1
  }
fi

./venv/bin/python manage.py runserver "0.0.0.0:8000" \
  > /tmp/micha-phone-dev-backend.log 2>&1 &
BACKEND_PID=$!

# Give Django a moment to bind so the frontend doesn't log proxy
# errors at startup.
sleep 1.5

# ── Start frontend ───────────────────────────────────────────────
cd "$ROOT/frontend"
if [ ! -d "node_modules" ]; then
  echo "❌ frontend/node_modules not found. Run: cd frontend && npm install"
  kill $BACKEND_PID 2>/dev/null || true
  exit 1
fi

# --host 0.0.0.0 binds Vite to all interfaces. --strictPort=false so
# Vite auto-shifts to 5174 if 5173 is busy.
npm run dev -- --host 0.0.0.0 &
FRONTEND_PID=$!

# ── Cleanup on exit ──────────────────────────────────────────────
cleanup() {
  echo ""
  echo "🛑 Stopping servers…"
  kill $FRONTEND_PID 2>/dev/null || true
  kill $BACKEND_PID 2>/dev/null || true
  wait 2>/dev/null
  exit 0
}
trap cleanup INT TERM

wait
